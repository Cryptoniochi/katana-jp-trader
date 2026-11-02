from datetime import date
from types import SimpleNamespace

from app.live.live_confirmed_entry_stop_recorder import (
    LiveConfirmedEntryStopDecision,
    LiveConfirmedEntryStopResult,
)
from app.live.live_entry_reconciliation_cycle import (
    LiveEntryReconciliationCycle,
)
from app.live.live_execution_journal_models import LiveExecutionState
from app.live.live_execution_tracking_flow import (
    LiveExecutionTrackingDecision,
)


class FakeRow:
    def __init__(
        self,
        *,
        execution_key="entry-1",
        trading_date=date(2026, 10, 30),
        quantity=100,
    ):
        self.execution_key = execution_key
        self.trading_date = trading_date
        self.quantity = quantity

    def to_order(self):
        return SimpleNamespace(code="7157", quantity=self.quantity)


class FakeRegistry:
    def __init__(self, row):
        self.row = row
        self.completed = []

    def list_pending(self):
        return [self.row]

    def complete(self, execution_key):
        self.completed.append(execution_key)


class FakeJournal:
    def get(self, execution_key):
        return SimpleNamespace(state=LiveExecutionState.SUBMITTED)


class FakeTrackingFlow:
    def __init__(
        self,
        *,
        row,
        actual_quantity,
        baseline_quantity=0,
        executed_quantity=100,
        terminal=True,
    ):
        self.row = row
        self.actual_quantity = actual_quantity
        self.baseline_quantity = baseline_quantity
        self.executed_quantity = executed_quantity
        self.terminal = terminal

    def reconcile(self, *, execution_key, order):
        reconciliation = SimpleNamespace(
            is_terminal=self.terminal,
            cumulative_quantity=self.executed_quantity,
        )
        lifecycle = SimpleNamespace(reconciliation=reconciliation)
        consistency = SimpleNamespace(
            baseline_quantity=self.baseline_quantity,
            executed_quantity=self.executed_quantity,
            expected_quantity=(
                self.baseline_quantity + self.executed_quantity
            ),
            actual_quantity=self.actual_quantity,
        )
        return SimpleNamespace(
            decision=LiveExecutionTrackingDecision.POSITION_MISMATCH,
            lifecycle=lifecycle,
            consistency=consistency,
        )


class BlockingStopRecorder:
    def __init__(self):
        self.calls = 0

    def record(self, **kwargs):
        self.calls += 1
        return LiveConfirmedEntryStopResult(
            decision=LiveConfirmedEntryStopDecision.BLOCKED,
            record=None,
            detail="position mismatch",
        )


class ForbiddenStopRecorder:
    def record(self, **kwargs):
        raise AssertionError(
            "Externally closed prior-day entry must not create a protective stop."
        )


def test_prior_day_terminal_buy_returned_to_baseline_is_completed():
    row = FakeRow()
    registry = FakeRegistry(row)

    cycle = LiveEntryReconciliationCycle(
        registry=registry,
        tracking_flow=FakeTrackingFlow(
            row=row,
            actual_quantity=0,
            baseline_quantity=0,
            executed_quantity=100,
            terminal=True,
        ),
        stop_recorder=ForbiddenStopRecorder(),
        journal=FakeJournal(),
    )

    result = cycle(date(2026, 11, 2))

    assert result.evaluated == 1
    assert result.completed == 1
    assert result.stops_recorded == 0
    assert result.blocked == 0
    assert registry.completed == ["entry-1"]


def test_same_day_position_mismatch_remains_fail_closed():
    row = FakeRow(trading_date=date(2026, 11, 2))
    registry = FakeRegistry(row)
    stop_recorder = BlockingStopRecorder()

    cycle = LiveEntryReconciliationCycle(
        registry=registry,
        tracking_flow=FakeTrackingFlow(
            row=row,
            actual_quantity=0,
            baseline_quantity=0,
            executed_quantity=100,
            terminal=True,
        ),
        stop_recorder=stop_recorder,
        journal=FakeJournal(),
    )

    result = cycle(date(2026, 11, 2))

    assert result.completed == 0
    assert result.blocked == 1
    assert registry.completed == []
    assert stop_recorder.calls == 1


def test_prior_day_mismatch_not_back_at_baseline_remains_fail_closed():
    row = FakeRow()
    registry = FakeRegistry(row)
    stop_recorder = BlockingStopRecorder()

    cycle = LiveEntryReconciliationCycle(
        registry=registry,
        tracking_flow=FakeTrackingFlow(
            row=row,
            actual_quantity=50,
            baseline_quantity=0,
            executed_quantity=100,
            terminal=True,
        ),
        stop_recorder=stop_recorder,
        journal=FakeJournal(),
    )

    result = cycle(date(2026, 11, 2))

    assert result.completed == 0
    assert result.blocked == 1
    assert registry.completed == []
    assert stop_recorder.calls == 1


def test_prior_day_nonterminal_mismatch_remains_fail_closed():
    row = FakeRow()
    registry = FakeRegistry(row)
    stop_recorder = BlockingStopRecorder()

    cycle = LiveEntryReconciliationCycle(
        registry=registry,
        tracking_flow=FakeTrackingFlow(
            row=row,
            actual_quantity=0,
            baseline_quantity=0,
            executed_quantity=100,
            terminal=False,
        ),
        stop_recorder=stop_recorder,
        journal=FakeJournal(),
    )

    result = cycle(date(2026, 11, 2))

    assert result.completed == 0
    assert result.blocked == 1
    assert registry.completed == []
    assert stop_recorder.calls == 1
