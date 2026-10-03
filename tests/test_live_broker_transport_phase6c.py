"""Phase 6-C Step 1 tests for the locked live broker transport."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

import app.live.live_broker_transport as transport_module
from app.live.execution_mode import (
    ExecutionModeSettings,
    TradingExecutionMode,
)
from app.live.live_broker_transport import (
    LockedLiveBrokerTransport,
)
from app.live.live_broker_transport_models import (
    LiveTransportDecision,
    LiveTransportLockReason,
    LiveTransportRequest,
)
from app.trading.order_models import OrderSide, OrderType, TradeOrder


NOW = datetime(2026, 10, 3, 1, 0, tzinfo=timezone.utc)
TRADING_DATE = date(2026, 10, 3)


def _order() -> TradeOrder:
    return TradeOrder(
        order_id="order-phase6c-1",
        signal_id="signal-phase6c-1",
        code="7203",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=100,
        limit_price=2500.0,
    )


def _request() -> LiveTransportRequest:
    return LiveTransportRequest(
        execution_key="execution-phase6c-1",
        order=_order(),
        requested_at=NOW,
    )


def _settings(
    *,
    mode: TradingExecutionMode = TradingExecutionMode.PAPER,
    live_armed: bool = False,
    confirmation: str | None = None,
) -> ExecutionModeSettings:
    return ExecutionModeSettings(
        mode=mode,
        live_armed=live_armed,
        live_confirmation=confirmation,
    )


def _transport(
    settings: ExecutionModeSettings | None = None,
    *,
    runtime_armed: bool = False,
) -> LockedLiveBrokerTransport:
    return LockedLiveBrokerTransport(
        execution_settings=settings or _settings(),
        runtime_armed=runtime_armed,
        now_provider=lambda: NOW,
    )


def test_static_transport_lock_is_disabled_by_default():
    assert transport_module.LIVE_BROKER_TRANSPORT_ENABLED is False

    result = _transport().evaluate(
        _request(),
        trading_date=TRADING_DATE,
    )

    assert result.decision is LiveTransportDecision.LOCKED
    assert result.reason is LiveTransportLockReason.STATIC_LOCK


def test_runtime_arm_is_independent_second_lock(monkeypatch):
    monkeypatch.setattr(
        transport_module,
        "LIVE_BROKER_TRANSPORT_ENABLED",
        True,
    )

    result = _transport(runtime_armed=False).evaluate(
        _request(),
        trading_date=TRADING_DATE,
    )

    assert result.decision is LiveTransportDecision.LOCKED
    assert result.reason is LiveTransportLockReason.RUNTIME_LOCK


@pytest.mark.parametrize(
    "settings",
    [
        _settings(mode=TradingExecutionMode.PAPER),
        _settings(mode=TradingExecutionMode.SHADOW),
        _settings(
            mode=TradingExecutionMode.LIVE,
            live_armed=False,
            confirmation=None,
        ),
        _settings(
            mode=TradingExecutionMode.LIVE,
            live_armed=True,
            confirmation="WRONG",
        ),
    ],
)
def test_execution_mode_daily_arming_policy_is_required(
    monkeypatch,
    settings,
):
    monkeypatch.setattr(
        transport_module,
        "LIVE_BROKER_TRANSPORT_ENABLED",
        True,
    )

    result = _transport(
        settings,
        runtime_armed=True,
    ).evaluate(
        _request(),
        trading_date=TRADING_DATE,
    )

    assert result.decision is LiveTransportDecision.LOCKED
    assert result.reason is LiveTransportLockReason.EXECUTION_MODE_LOCK


def test_even_fully_armed_configuration_has_no_transport(monkeypatch):
    monkeypatch.setattr(
        transport_module,
        "LIVE_BROKER_TRANSPORT_ENABLED",
        True,
    )

    settings = _settings(
        mode=TradingExecutionMode.LIVE,
        live_armed=True,
        confirmation="KATANA-LIVE-2026-10-03",
    )

    result = _transport(
        settings,
        runtime_armed=True,
    ).evaluate(
        _request(),
        trading_date=TRADING_DATE,
    )

    assert result.decision is LiveTransportDecision.LOCKED
    assert result.reason is LiveTransportLockReason.NO_TRANSPORT


def test_request_requires_timezone_aware_timestamp():
    with pytest.raises(ValueError, match="timezone-aware"):
        LiveTransportRequest(
            execution_key="execution-phase6c-1",
            order=_order(),
            requested_at=datetime(2026, 10, 3, 1, 0),
        )


def test_transport_rejects_naive_now_provider():
    service = LockedLiveBrokerTransport(
        execution_settings=_settings(),
        now_provider=lambda: datetime(2026, 10, 3, 1, 0),
    )

    with pytest.raises(ValueError, match="timezone-aware"):
        service.evaluate(
            _request(),
            trading_date=TRADING_DATE,
        )


def test_locked_transport_accepts_no_transport_dependency():
    init_names = LockedLiveBrokerTransport.__init__.__code__.co_varnames

    assert "broker" not in init_names
    assert "broker_adapter" not in init_names
    assert "client" not in init_names
    assert "transport" not in init_names


def test_locked_transport_exposes_no_submission_method():
    forbidden = (
        "submit_order",
        "send_order",
        "sendorder",
        "transmit",
        "execute_live_order",
    )

    for name in forbidden:
        assert not hasattr(LockedLiveBrokerTransport, name)
