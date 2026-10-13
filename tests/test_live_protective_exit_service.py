from dataclasses import dataclass
from datetime import date, datetime, timezone

from app.live.live_protective_exit_service import (
    LiveProtectiveExitDecision,
    LiveProtectiveExitReason,
    LiveProtectiveExitService,
)
from app.trading.order_models import OrderSide, OrderType


NOW = datetime(2026, 10, 13, 6, 30, tzinfo=timezone.utc)
DAY = date(2026, 10, 13)


@dataclass(frozen=True)
class Position:
    code: str
    quantity: int


@dataclass(frozen=True)
class Snapshot:
    positions: tuple[Position, ...]
    is_complete: bool = True
    is_stale: bool = False


class Provider:
    def __init__(self, snapshot=None, error=None):
        self.value = snapshot
        self.error = error
        self.calls = 0

    def snapshot(self):
        self.calls += 1
        if self.error:
            raise self.error
        return self.value


def service(snapshot, price=200.0):
    return LiveProtectiveExitService(
        account_state_provider=Provider(snapshot),
        market_price_provider=lambda code: price,
        now_provider=lambda: NOW,
    )


def test_stop_loss_uses_actual_live_position_quantity():
    result = service(Snapshot((Position("3911", 100),)), price=199).evaluate_stop_loss(
        code="3911", stop_price=200, trading_date=DAY
    )
    assert result.decision is LiveProtectiveExitDecision.EXIT_REQUIRED
    assert result.reason is LiveProtectiveExitReason.STOP_LOSS
    assert result.quantity == 100
    assert result.order is not None
    assert result.order.side is OrderSide.SELL
    assert result.order.order_type is OrderType.MARKET
    assert result.order.quantity == 100


def test_stop_loss_holds_above_trigger():
    result = service(Snapshot((Position("3911", 100),)), price=201).evaluate_stop_loss(
        code="3911", stop_price=200, trading_date=DAY
    )
    assert result.decision is LiveProtectiveExitDecision.HOLD
    assert result.order is None


def test_stop_loss_does_not_create_exit_for_missing_real_position():
    result = service(Snapshot(tuple()), price=190).evaluate_stop_loss(
        code="3911", stop_price=200, trading_date=DAY
    )
    assert result.decision is LiveProtectiveExitDecision.NO_POSITION
    assert result.order is None


def test_duplicate_live_position_rows_are_aggregated():
    result = service(
        Snapshot((Position("3911", 100), Position("3911", 200))), price=190
    ).evaluate_stop_loss(code="3911", stop_price=200, trading_date=DAY)
    assert result.quantity == 300
    assert result.order.quantity == 300


def test_account_read_failure_blocks_without_order():
    provider = Provider(error=RuntimeError("offline"))
    svc = LiveProtectiveExitService(
        account_state_provider=provider,
        market_price_provider=lambda code: 190,
        now_provider=lambda: NOW,
    )
    result = svc.evaluate_stop_loss(
        code="3911", stop_price=200, trading_date=DAY
    )
    assert result.decision is LiveProtectiveExitDecision.BLOCKED
    assert result.order is None


def test_stale_account_snapshot_blocks_without_order():
    result = service(
        Snapshot((Position("3911", 100),), is_stale=True), price=190
    ).evaluate_stop_loss(code="3911", stop_price=200, trading_date=DAY)
    assert result.decision is LiveProtectiveExitDecision.BLOCKED
    assert result.order is None


def test_market_price_failure_blocks_stop_exit():
    svc = LiveProtectiveExitService(
        account_state_provider=Provider(Snapshot((Position("3911", 100),))),
        market_price_provider=lambda code: (_ for _ in ()).throw(RuntimeError("no price")),
        now_provider=lambda: NOW,
    )
    result = svc.evaluate_stop_loss(
        code="3911", stop_price=200, trading_date=DAY
    )
    assert result.decision is LiveProtectiveExitDecision.BLOCKED
    assert result.order is None


def test_end_of_day_plans_every_actual_live_position():
    batch = service(
        Snapshot((Position("3911", 100), Position("7203", 200)))
    ).plan_end_of_day(trading_date=DAY)
    assert batch.is_blocked is False
    assert [(o.code, o.quantity) for o in batch.exit_orders] == [
        ("3911", 100),
        ("7203", 200),
    ]
    assert all(o.side is OrderSide.SELL for o in batch.exit_orders)
    assert all(o.order_type is OrderType.MARKET for o in batch.exit_orders)


def test_end_of_day_empty_account_creates_no_orders():
    batch = service(Snapshot(tuple())).plan_end_of_day(trading_date=DAY)
    assert batch.plans == tuple()
    assert batch.exit_orders == tuple()
    assert batch.is_blocked is False


def test_end_of_day_account_failure_is_fail_closed():
    svc = LiveProtectiveExitService(
        account_state_provider=Provider(error=RuntimeError("offline")),
        market_price_provider=lambda code: 1,
        now_provider=lambda: NOW,
    )
    batch = svc.plan_end_of_day(trading_date=DAY)
    assert batch.is_blocked is True
    assert batch.exit_orders == tuple()


def test_exit_service_has_no_submission_or_transport_method():
    forbidden = {
        "send", "send_order", "sendorder", "submit", "submit_order",
        "transmit", "execute_live_order",
    }
    public = {name.lower() for name in dir(LiveProtectiveExitService) if not name.startswith("_")}
    assert forbidden.isdisjoint(public)
