import json
from datetime import datetime, timezone
from pathlib import Path

from app.live.live_activation_authorization import (
    LiveActivationAuthorizationItem,
    LiveActivationAuthorizationReport,
    LiveActivationAuthorizationState,
)
from app.live.live_activation_operator_review import LiveActivationOperatorReview
from app.live.live_broker_transport import LIVE_BROKER_TRANSPORT_ENABLED
from app.live.live_order_adapter import LIVE_ORDER_TRANSMISSION_ENABLED
from app.live.locked_live_runtime_integration import (
    LOCKED_LIVE_RUNTIME_INTEGRATION_ENABLED,
)


NOW = datetime(2026, 10, 7, 11, 0, tzinfo=timezone.utc)


class FakeGate:
    def __init__(self, report):
        self.report = report
        self.calls = 0

    def check(self):
        self.calls += 1
        return self.report


def make_report(*, ready=True):
    return LiveActivationAuthorizationReport(
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


def test_construction_is_inert():
    gate = FakeGate(make_report())
    review = LiveActivationOperatorReview(gate=gate)
    assert review is not None
    assert gate.calls == 0


def test_evaluate_calls_gate_exactly_once():
    gate = FakeGate(make_report())
    review = LiveActivationOperatorReview(gate=gate)
    report = review.evaluate()
    assert report.authorization_ready is True
    assert gate.calls == 1


def test_ready_report_is_rendered_for_human_review():
    payload = LiveActivationOperatorReview.to_dict(make_report())
    assert payload["authorization_ready"] is True
    assert payload["state"] == "authorization_ready"
    assert payload["items"][0]["key"] == "example"
    assert "READ-ONLY REVIEW ONLY" in payload["operator_notice"]


def test_blocked_report_preserves_blocked_state():
    payload = LiveActivationOperatorReview.to_dict(make_report(ready=False))
    assert payload["authorization_ready"] is False
    assert payload["state"] == "blocked"
    assert payload["items"][0]["passed"] is False


def test_json_output_is_valid_and_contains_explicit_non_activation_notice():
    text = LiveActivationOperatorReview.to_json(make_report())
    payload = json.loads(text)
    assert payload["generated_at"] == NOW.isoformat()
    assert "does not enable" in payload["operator_notice"]


def test_rendering_does_not_change_any_hard_lock():
    before = (
        LIVE_ORDER_TRANSMISSION_ENABLED,
        LIVE_BROKER_TRANSPORT_ENABLED,
        LOCKED_LIVE_RUNTIME_INTEGRATION_ENABLED,
    )
    LiveActivationOperatorReview.to_json(make_report())
    after = (
        LIVE_ORDER_TRANSMISSION_ENABLED,
        LIVE_BROKER_TRANSPORT_ENABLED,
        LOCKED_LIVE_RUNTIME_INTEGRATION_ENABLED,
    )
    assert before == after == (False, False, False)


def test_operator_review_source_has_no_unlock_execution_or_network_path():
    source = Path(
        "app/live/live_activation_operator_review.py"
    ).read_text(encoding="utf-8").lower()
    forbidden = (
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
        "enabled = true",
        "subprocess",
        "socket.",
    )
    assert all(token not in source for token in forbidden)


def test_report_boundary_does_not_write_files():
    source = Path(
        "app/live/live_activation_operator_review.py"
    ).read_text(encoding="utf-8").lower()
    forbidden = (
        "write_text(",
        "write_bytes(",
        "open(",
        "unlink(",
        "replace(",
        "rename(",
    )
    assert all(token not in source for token in forbidden)
