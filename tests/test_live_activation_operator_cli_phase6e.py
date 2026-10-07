import io
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.live.live_activation_authorization import (
    LiveActivationAuthorizationItem,
    LiveActivationAuthorizationReport,
    LiveActivationAuthorizationState,
)
from app.live.live_broker_transport import LIVE_BROKER_TRANSPORT_ENABLED
from app.live.live_order_adapter import LIVE_ORDER_TRANSMISSION_ENABLED
from app.live.locked_live_runtime_integration import (
    LOCKED_LIVE_RUNTIME_INTEGRATION_ENABLED,
)
from app.run_live_activation_review import build_parser, main, run_once


NOW = datetime(2026, 10, 7, 11, 30, tzinfo=timezone.utc)


class FakeReview:
    def __init__(self, *, ready):
        self.calls = 0
        self.report = LiveActivationAuthorizationReport(
            generated_at=NOW,
            authorization_ready=ready,
            state=(
                LiveActivationAuthorizationState.AUTHORIZATION_READY
                if ready
                else LiveActivationAuthorizationState.BLOCKED
            ),
            items=(
                LiveActivationAuthorizationItem(
                    key="example",
                    passed=ready,
                    message="ready" if ready else "blocked",
                ),
            ),
        )

    def evaluate(self):
        self.calls += 1
        return self.report


def test_run_once_evaluates_exactly_once_and_prints_json():
    review = FakeReview(ready=True)
    output = io.StringIO()
    code = run_once(review=review, output=output)
    payload = json.loads(output.getvalue())
    assert code == 0
    assert review.calls == 1
    assert payload["authorization_ready"] is True
    assert "READ-ONLY REVIEW ONLY" in payload["operator_notice"]


def test_blocked_review_returns_nonzero_without_exception():
    review = FakeReview(ready=False)
    output = io.StringIO()
    code = run_once(review=review, output=output)
    payload = json.loads(output.getvalue())
    assert code == 2
    assert review.calls == 1
    assert payload["state"] == "blocked"


def test_parser_exposes_no_unlock_or_order_arguments():
    parser = build_parser()
    option_strings = {
        option
        for action in parser._actions
        for option in action.option_strings
    }
    forbidden = {
        "--enable",
        "--unlock",
        "--release",
        "--arm",
        "--submit",
        "--send-order",
        "--recover",
        "--start-runtime",
    }
    assert option_strings.isdisjoint(forbidden)


def test_main_is_not_attached_to_production_composition(capsys):
    with pytest.raises(SystemExit) as error:
        main([])
    assert error.value.code == 2
    captured = capsys.readouterr()
    assert "Production composition is intentionally not attached yet" in captured.err


def test_cli_boundary_keeps_all_hard_locks_closed():
    output = io.StringIO()
    run_once(review=FakeReview(ready=True), output=output)
    assert LIVE_ORDER_TRANSMISSION_ENABLED is False
    assert LIVE_BROKER_TRANSPORT_ENABLED is False
    assert LOCKED_LIVE_RUNTIME_INTEGRATION_ENABLED is False


def test_cli_source_has_no_production_runtime_or_network_path():
    source = Path("app/run_live_activation_review.py").read_text(
        encoding="utf-8"
    ).lower()
    forbidden = (
        "papertradingcomposition",
        "papertradingproductionsettings",
        "sendorder",
        "send_order(",
        "submit_order(",
        "requests.",
        "httpx.",
        "urllib.",
        ".release(",
        ".recover(",
        ".run_once(",
        ".process(",
        "runtime_armed",
        "kabu_station_client",
        "socket.",
    )
    assert all(token not in source for token in forbidden)


def test_cli_source_has_no_file_mutation_path():
    source = Path("app/run_live_activation_review.py").read_text(
        encoding="utf-8"
    ).lower()
    forbidden = (
        "write_text(",
        "write_bytes(",
        "unlink(",
        "replace(",
        "rename(",
    )
    assert all(token not in source for token in forbidden)
