from __future__ import annotations

import inspect
from datetime import date
from pathlib import Path

import pytest

from app.live.live_dry_run_operator_composition import (
    LiveDryRunOperatorComposition,
    LiveDryRunOperatorPaths,
)
from app.live.live_order_adapter import LIVE_ORDER_TRANSMISSION_ENABLED
from app.live.live_broker_transport import LIVE_BROKER_TRANSPORT_ENABLED
from app.live.locked_live_runtime_integration import (
    LOCKED_LIVE_RUNTIME_INTEGRATION_ENABLED,
)
from app.run_live_dry_run_operator import (
    DRY_RUN_CONFIRMATION,
    build_parser,
    request_from_args,
    validate_live_confirmation,
)


def test_hard_locks_remain_false():
    assert LIVE_ORDER_TRANSMISSION_ENABLED is False
    assert LIVE_BROKER_TRANSPORT_ENABLED is False
    assert LOCKED_LIVE_RUNTIME_INTEGRATION_ENABLED is False


def test_default_dry_run_database_is_isolated():
    paths = LiveDryRunOperatorPaths()
    assert paths.database_path == Path("data/live_dry_run.db")
    assert paths.database_path != Path("data/katana.db")


def test_production_database_cannot_be_execution_database():
    with pytest.raises(ValueError):
        LiveDryRunOperatorPaths(database_path=Path("data/katana.db"))


def test_cli_preserves_step6cb_order_surface():
    args = build_parser().parse_args([
        "--trading-date", "2026-10-05",
        "--order-id", "o1",
        "--signal-id", "s1",
        "--code", "7203",
        "--side", "buy",
        "--order-type", "limit",
        "--quantity", "100",
        "--limit-price", "3000",
        "--idempotency-key", "dry-1",
        "--confirm", DRY_RUN_CONFIRMATION,
        "--live-confirmation", "KATANA-LIVE-2026-10-05",
    ])
    request = request_from_args(args)
    assert request.order.code == "7203"
    assert request.idempotency_key == "dry-1"


def test_daily_live_confirmation_is_exact():
    trading_date = date(2026, 10, 5)
    validate_live_confirmation(trading_date, "KATANA-LIVE-2026-10-05")
    with pytest.raises(ValueError):
        validate_live_confirmation(trading_date, "KATANA-LIVE-2026-10-04")


def test_production_factory_is_explicit_read_only_bridge():
    source = inspect.getsource(
        LiveDryRunOperatorComposition.create_from_production_read_only
    )
    assert "ProductionDryRunReadOnlyFactory.create" in source
    assert "LiveDryRunOperatorComposition.create" in source


def test_cli_and_composition_have_no_real_transmission_primitives():
    source = (
        Path("app/run_live_dry_run_operator.py").read_text(encoding="utf-8")
        + Path("app/live/live_dry_run_operator_composition.py").read_text(
            encoding="utf-8"
        )
    ).lower()
    forbidden = (
        "requests.", "httpx.", "urllib.", "kabustationclient",
        "brokeradapter", "sendorder", "send_order", ".post(", ".put(",
        ".request(", "mark_submitted",
    )
    for token in forbidden:
        assert token not in source
