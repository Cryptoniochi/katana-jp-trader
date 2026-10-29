from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

from app.live.activated_live_submission_coordinator import (
    ActivatedLiveSubmissionDecision,
)
from app.live.live_account_state_service import (
    LiveAccountState,
    LiveCashPosition,
)
from app.live.live_execution_position_consistency import (
    LiveExecutionPositionConsistencyService,
)
from app.live.live_execution_reconciliation import (
    LiveExecutionFill,
    LiveExecutionReconciliation,
    LiveExecutionReconciliationService,
    LiveExecutionReconciliationState,
)
from app.live.live_execution_tracking_flow import (
    LiveExecutionTrackingDecision,
    LiveExecutionTrackingFlow,
    SQLiteLivePositionBaselineRepository,
)
from app.live.live_submitted_execution_lifecycle import (
    LiveSubmittedExecutionDecision,
)
from app.trading.order_models import (
    OrderSide,
    OrderType,
    TradeOrder,
)
from app.trading.trade_execution_repository import (
    DuplicateTradeExecutionError,
)


UTC = timezone.utc
JST = timezone(timedelta(hours=9))
NOW = datetime(2026, 10, 29, 2, 2, 24, tzinfo=UTC)
DAY = date(2026, 10, 29)


class FakeClient:
    def __init__(self, orders):
        self._orders = tuple(orders)

    def orders(self, *, product=0):
        return self._orders


def test_rectype8_extracts_execution_day():
    result = LiveExecutionReconciliationService(
        client=FakeClient(
            (
                {
                    "ID": "B1",
                    "OrderQty": 100,
                    "CumQty": 100,
                    "OrderState": 5,
                    "Details": [
                        {
                            "RecType": 8,
                            "Qty": 100,
                            "Price": 1525.5,
                            "ExecutionID": "E2026102903VY6",
                            "ExecutionDay":
                                "2026-10-29T11:02:24.592+09:00",
                        }
                    ],
                },
            )
        ),
        product=0,
    ).reconcile("B1")

    fill = result.fills[0]
    assert fill.execution_id == "E2026102903VY6"
    assert fill.quantity == 100
    assert fill.price == 1525.5
    assert fill.executed_at == datetime(
        2026, 10, 29, 11, 2, 24, 592000, tzinfo=JST
    )


class Account:
    def __init__(self, *states):
        self.states = list(states)

    def refresh(self):
        return self.states.pop(0)


class Submission:
    def submit(self, **kwargs):
        return SimpleNamespace(
            decision=ActivatedLiveSubmissionDecision.SUBMITTED
        )


class Lifecycle:
    def __init__(self, reconciliation):
        self.reconciliation = reconciliation

    def reconcile(self, execution_key):
        mapping = {
            LiveExecutionReconciliationState.ACCEPTED:
                LiveSubmittedExecutionDecision.WORKING,
            LiveExecutionReconciliationState.PARTIALLY_FILLED:
                LiveSubmittedExecutionDecision.PARTIALLY_FILLED,
            LiveExecutionReconciliationState.FILLED:
                LiveSubmittedExecutionDecision.FILLED,
            LiveExecutionReconciliationState.TERMINATED_UNFILLED:
                LiveSubmittedExecutionDecision.TERMINATED_UNFILLED,
            LiveExecutionReconciliationState.TERMINATED_PARTIAL:
                LiveSubmittedExecutionDecision.TERMINATED_PARTIAL,
            LiveExecutionReconciliationState.UNKNOWN:
                LiveSubmittedExecutionDecision.UNKNOWN,
        }
        return SimpleNamespace(
            decision=mapping[self.reconciliation.state],
            reconciliation=self.reconciliation,
        )


class MemoryRepository:
    def __init__(self):
        self.records = {}

    def save(self, execution):
        if execution.execution_id in self.records:
            raise DuplicateTradeExecutionError("duplicate")
        record = SimpleNamespace(execution=execution)
        self.records[execution.execution_id] = record
        return record

    def get(self, execution_id):
        return self.records[execution_id]


def state(quantity):
    positions = (
        ()
        if quantity == 0
        else (
            LiveCashPosition(
                code="2395",
                quantity=quantity,
                average_price=1525.5,
                current_price=1525.5,
            ),
        )
    )
    return LiveAccountState(
        generated_at=NOW,
        cash_balance=900000.0,
        positions=positions,
        orders=(),
    )


def order(side=OrderSide.BUY):
    return TradeOrder(
        order_id="live-order-1",
        signal_id="pullback-live-signal-1",
        code="2395",
        side=side,
        order_type=OrderType.MARKET,
        quantity=100,
    )


def reconciliation():
    return LiveExecutionReconciliation(
        broker_order_id="20261029A01N98206011",
        state=LiveExecutionReconciliationState.FILLED,
        order_quantity=100.0,
        cumulative_quantity=100.0,
        remaining_quantity=0.0,
        fills=(
            LiveExecutionFill(
                execution_id="E2026102903VY6",
                quantity=100.0,
                price=1525.5,
                executed_at=datetime(
                    2026,
                    10,
                    29,
                    11,
                    2,
                    24,
                    592000,
                    tzinfo=JST,
                ),
            ),
        ),
        detail="test",
    )


def test_consistent_buy_fill_is_recorded_once(tmp_path):
    repo = MemoryRepository()
    flow = LiveExecutionTrackingFlow(
        baseline_repository=SQLiteLivePositionBaselineRepository(
            tmp_path / "katana.db"
        ),
        position_consistency_service=(
            LiveExecutionPositionConsistencyService(
                account_state_service=Account(
                    state(0),
                    state(100),
                    state(100),
                )
            )
        ),
        submission_coordinator=Submission(),
        submitted_lifecycle=Lifecycle(reconciliation()),
        execution_repository=repo,
    )

    flow.submit(
        execution_key="entry-1",
        order=order(),
        trading_date=DAY,
        required_baseline_quantity=0,
    )

    first = flow.reconcile(
        execution_key="entry-1",
        order=order(),
    )
    second = flow.reconcile(
        execution_key="entry-1",
        order=order(),
    )

    assert (
        first.decision
        is LiveExecutionTrackingDecision.FILLED_CONSISTENT
    )
    assert (
        second.decision
        is LiveExecutionTrackingDecision.FILLED_CONSISTENT
    )
    assert len(repo.records) == 1

    execution = repo.records[
        "E2026102903VY6"
    ].execution

    assert execution.broker_order_id == (
        "20261029A01N98206011"
    )
    assert execution.quantity == 100
    assert execution.execution_price == 1525.5
    assert execution.broker_name == "kabu-station"


def test_position_mismatch_does_not_record_fill(tmp_path):
    repo = MemoryRepository()
    flow = LiveExecutionTrackingFlow(
        baseline_repository=SQLiteLivePositionBaselineRepository(
            tmp_path / "katana.db"
        ),
        position_consistency_service=(
            LiveExecutionPositionConsistencyService(
                account_state_service=Account(
                    state(0),
                    state(50),
                )
            )
        ),
        submission_coordinator=Submission(),
        submitted_lifecycle=Lifecycle(reconciliation()),
        execution_repository=repo,
    )

    flow.submit(
        execution_key="entry-1",
        order=order(),
        trading_date=DAY,
        required_baseline_quantity=0,
    )

    result = flow.reconcile(
        execution_key="entry-1",
        order=order(),
    )

    assert (
        result.decision
        is LiveExecutionTrackingDecision.POSITION_MISMATCH
    )
    assert repo.records == {}
