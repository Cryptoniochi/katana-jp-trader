"""Phase 6-D Step 6C-B explicit operator CLI boundary tests."""

import inspect
from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

from app.live.live_dry_run_operational_models import LiveDryRunAuditState
from app.run_live_dry_run_operator import (
    DRY_RUN_CONFIRMATION,
    LiveDryRunOperator,
    LiveDryRunOperatorRequest,
    format_record,
    main,
    parse_request,
)
from app.trading.order_models import OrderSide, OrderType, TradeOrder


NOW = datetime(2026, 10, 5, 10, 0, tzinfo=timezone.utc)


def _argv(confirm=DRY_RUN_CONFIRMATION):
    return [
        "--trading-date", "2026-10-05",
        "--order-id", "dry-order-1",
        "--signal-id", "dry-signal-1",
        "--code", "7203",
        "--side", "buy",
        "--order-type", "limit",
        "--quantity", "100",
        "--limit-price", "3000",
        "--idempotency-key", "dry-key-1",
        "--confirm", confirm,
    ]


def test_parse_request_requires_exact_confirmation():
    request = parse_request(_argv())
    assert request.confirmation == DRY_RUN_CONFIRMATION
    assert request.order.code == "7203"
    assert request.order.side is OrderSide.BUY
    assert request.order.order_type is OrderType.LIMIT
    assert request.order.quantity == 100
    assert request.order.limit_price == 3000.0

    with pytest.raises(ValueError):
        parse_request(_argv("dry-run"))


def test_operator_constructs_intent_and_calls_injected_audited_service():
    captured = {}

    class Service:
        def run(self, *, intent, trading_date):
            captured["intent"] = intent
            captured["trading_date"] = trading_date
            return "audit-result"

    request = parse_request(_argv())
    result = LiveDryRunOperator(
        service_provider=lambda: Service(),
        now_provider=lambda: NOW,
    ).execute(request)

    assert result == "audit-result"
    assert captured["intent"].order is request.order
    assert captured["intent"].idempotency_key == "dry-key-1"
    assert captured["intent"].created_at == NOW
    assert captured["trading_date"] == date(2026, 10, 5)


def test_invalid_trade_order_is_rejected_before_service_access():
    calls = 0

    def provider():
        nonlocal calls
        calls += 1
        raise AssertionError("service must not be reached")

    with pytest.raises(ValueError):
        parse_request([
            "--trading-date", "2026-10-05",
            "--order-id", "o",
            "--signal-id", "s",
            "--code", "7203",
            "--side", "buy",
            "--order-type", "market",
            "--quantity", "100",
            "--limit-price", "3000",
            "--idempotency-key", "k",
            "--confirm", "DRY-RUN",
        ])
    assert calls == 0


def test_standalone_main_fails_closed_without_production_composition():
    with pytest.raises(SystemExit) as error:
        main(_argv())
    text = str(error.value)
    assert "not connected to production state" in text
    assert "No dry-run was executed" in text


def test_format_record_makes_no_transmission_explicit():
    record = SimpleNamespace(
        state=LiveDryRunAuditState.SIMULATED_TRANSPORT_REACHED,
        trading_date="2026-10-05",
        execution_key="key",
        order_id="order",
        signal_id="signal",
        readiness_activation_ready=True,
        readiness_transport_ready=False,
        readiness_live_order_ready=False,
        journal_state="submission_pending",
        simulated_broker_order_id="DRYRUN-abc",
        message="simulated",
    )
    text = format_record(record)
    assert "readiness_transport_ready=false" in text
    assert "readiness_live_order_ready=false" in text
    assert "broker_transmission_occurred=false" in text


def test_cli_module_contains_no_network_broker_or_submit_primitive():
    import app.run_live_dry_run_operator as module

    source = inspect.getsource(module)
    for token in (
        "requests.", "httpx.", "urllib.", "KabuStationClient",
        "BrokerAdapter", "mark_submitted", ".post(", ".put(", ".request(",
    ):
        assert token not in source
