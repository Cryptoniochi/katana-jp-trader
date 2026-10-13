from datetime import datetime, timezone

from app.live.live_account_state_service import LiveAccountState, LiveCashPosition
from app.live.live_execution_position_consistency import (
    LiveExecutionPositionConsistencyDecision,
    LiveExecutionPositionConsistencyService,
    LivePositionBaseline,
)
from app.live.live_execution_reconciliation import (
    LiveExecutionReconciliation,
    LiveExecutionReconciliationState,
)
from app.trading.order_models import OrderSide, OrderType, TradeOrder

NOW = datetime(2026, 10, 13, 6, 0, tzinfo=timezone.utc)


def _order(side=OrderSide.BUY, quantity=100):
    return TradeOrder(
        order_id="order-1",
        signal_id="signal-1",
        code="3911",
        side=side,
        order_type=OrderType.LIMIT,
        quantity=quantity,
        limit_price=211.0,
    )


def _state(quantity):
    positions = () if quantity == 0 else (
        LiveCashPosition(
            code="3911",
            quantity=quantity,
            average_price=211.0,
            current_price=211.0,
        ),
    )
    return LiveAccountState(
        generated_at=NOW,
        cash_balance=900_000.0,
        positions=positions,
        orders=(),
    )


def _reconciliation(state, cumulative, order_quantity=100):
    return LiveExecutionReconciliation(
        broker_order_id="broker-1",
        state=state,
        order_quantity=float(order_quantity) if order_quantity is not None else None,
        cumulative_quantity=float(cumulative) if cumulative is not None else None,
        remaining_quantity=(
            float(order_quantity - cumulative)
            if order_quantity is not None and cumulative is not None
            else None
        ),
        fills=(),
        detail="test",
    )


class _AccountStateService:
    def __init__(self, *states):
        self.states = list(states)
        self.calls = 0

    def refresh(self):
        self.calls += 1
        value = self.states.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


def test_capture_baseline_reads_real_position():
    account = _AccountStateService(_state(200))
    service = LiveExecutionPositionConsistencyService(account_state_service=account)

    baseline = service.capture_baseline(_order())

    assert baseline == LivePositionBaseline(code="3911", quantity=200)
    assert account.calls == 1


def test_filled_buy_matches_real_position_delta():
    account = _AccountStateService(_state(300))
    service = LiveExecutionPositionConsistencyService(account_state_service=account)

    result = service.verify(
        order=_order(OrderSide.BUY),
        baseline=LivePositionBaseline("3911", 200),
        reconciliation=_reconciliation(LiveExecutionReconciliationState.FILLED, 100),
    )

    assert result.decision is LiveExecutionPositionConsistencyDecision.CONSISTENT
    assert result.expected_quantity == 300
    assert result.actual_quantity == 300
    assert result.may_proceed is True
    assert result.may_retry_submission is False


def test_filled_sell_to_flat_matches_zero_position():
    account = _AccountStateService(_state(0))
    service = LiveExecutionPositionConsistencyService(account_state_service=account)

    result = service.verify(
        order=_order(OrderSide.SELL),
        baseline=LivePositionBaseline("3911", 100),
        reconciliation=_reconciliation(LiveExecutionReconciliationState.FILLED, 100),
    )

    assert result.decision is LiveExecutionPositionConsistencyDecision.CONSISTENT
    assert result.expected_quantity == 0
    assert result.actual_quantity == 0


def test_partial_buy_uses_cumulative_execution_quantity():
    account = _AccountStateService(_state(150))
    service = LiveExecutionPositionConsistencyService(account_state_service=account)

    result = service.verify(
        order=_order(OrderSide.BUY),
        baseline=LivePositionBaseline("3911", 100),
        reconciliation=_reconciliation(LiveExecutionReconciliationState.PARTIALLY_FILLED, 50),
    )

    assert result.decision is LiveExecutionPositionConsistencyDecision.CONSISTENT
    assert result.executed_quantity == 50
    assert result.expected_quantity == 150


def test_terminated_partial_sell_uses_executed_delta():
    account = _AccountStateService(_state(60))
    service = LiveExecutionPositionConsistencyService(account_state_service=account)

    result = service.verify(
        order=_order(OrderSide.SELL),
        baseline=LivePositionBaseline("3911", 100),
        reconciliation=_reconciliation(LiveExecutionReconciliationState.TERMINATED_PARTIAL, 40),
    )

    assert result.decision is LiveExecutionPositionConsistencyDecision.CONSISTENT
    assert result.expected_quantity == 60


def test_unfilled_terminal_order_requires_unchanged_position():
    account = _AccountStateService(_state(100))
    service = LiveExecutionPositionConsistencyService(account_state_service=account)

    result = service.verify(
        order=_order(OrderSide.SELL),
        baseline=LivePositionBaseline("3911", 100),
        reconciliation=_reconciliation(LiveExecutionReconciliationState.TERMINATED_UNFILLED, 0),
    )

    assert result.decision is LiveExecutionPositionConsistencyDecision.CONSISTENT
    assert result.expected_quantity == 100


def test_position_mismatch_fails_closed():
    account = _AccountStateService(_state(250))
    service = LiveExecutionPositionConsistencyService(account_state_service=account)

    result = service.verify(
        order=_order(OrderSide.BUY),
        baseline=LivePositionBaseline("3911", 200),
        reconciliation=_reconciliation(LiveExecutionReconciliationState.FILLED, 100),
    )

    assert result.decision is LiveExecutionPositionConsistencyDecision.MISMATCH
    assert result.expected_quantity == 300
    assert result.actual_quantity == 250
    assert result.may_proceed is False
    assert result.may_retry_submission is False


def test_unknown_execution_does_not_read_position_and_fails_closed():
    account = _AccountStateService(_state(100))
    service = LiveExecutionPositionConsistencyService(account_state_service=account)

    result = service.verify(
        order=_order(),
        baseline=LivePositionBaseline("3911", 0),
        reconciliation=_reconciliation(LiveExecutionReconciliationState.UNKNOWN, None, None),
    )

    assert result.decision is LiveExecutionPositionConsistencyDecision.UNKNOWN
    assert result.may_proceed is False
    assert account.calls == 0


def test_position_refresh_failure_is_unknown_and_never_retry_permission():
    account = _AccountStateService(RuntimeError("offline"))
    service = LiveExecutionPositionConsistencyService(account_state_service=account)

    result = service.verify(
        order=_order(),
        baseline=LivePositionBaseline("3911", 0),
        reconciliation=_reconciliation(LiveExecutionReconciliationState.FILLED, 100),
    )

    assert result.decision is LiveExecutionPositionConsistencyDecision.UNKNOWN
    assert result.actual_quantity is None
    assert result.may_retry_submission is False


def test_sell_execution_cannot_exceed_baseline_position():
    account = _AccountStateService(_state(0))
    service = LiveExecutionPositionConsistencyService(account_state_service=account)

    result = service.verify(
        order=_order(OrderSide.SELL),
        baseline=LivePositionBaseline("3911", 50),
        reconciliation=_reconciliation(LiveExecutionReconciliationState.FILLED, 100),
    )

    assert result.decision is LiveExecutionPositionConsistencyDecision.UNKNOWN
    assert result.may_proceed is False
    assert account.calls == 0
