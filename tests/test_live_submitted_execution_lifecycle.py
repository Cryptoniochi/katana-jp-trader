from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.live.live_execution_journal_repository import (
    LiveExecutionTransitionError,
    SQLiteLiveExecutionJournal,
)
from app.live.live_execution_reconciliation import (
    LiveExecutionReconciliation,
    LiveExecutionReconciliationState,
)
from app.live.live_submitted_execution_lifecycle import (
    LiveSubmittedExecutionDecision,
    LiveSubmittedExecutionLifecycle,
)

NOW = datetime(2026, 10, 13, 6, 0, tzinfo=timezone.utc)
BROKER_ID = "20261013A01N72502164"


class FakeReconciler:
    def __init__(self, state: LiveExecutionReconciliationState) -> None:
        self.state = state
        self.calls = []

    def reconcile(self, broker_order_id: str) -> LiveExecutionReconciliation:
        self.calls.append(broker_order_id)
        qty = 100.0
        cum = {
            LiveExecutionReconciliationState.ACCEPTED: 0.0,
            LiveExecutionReconciliationState.PARTIALLY_FILLED: 40.0,
            LiveExecutionReconciliationState.FILLED: 100.0,
            LiveExecutionReconciliationState.TERMINATED_UNFILLED: 0.0,
            LiveExecutionReconciliationState.TERMINATED_PARTIAL: 40.0,
        }.get(self.state)
        return LiveExecutionReconciliation(
            broker_order_id=broker_order_id,
            state=self.state,
            order_quantity=qty if cum is not None else None,
            cumulative_quantity=cum,
            remaining_quantity=(qty - cum) if cum is not None else None,
            fills=(),
            detail="fixture",
        )


def submitted_journal(tmp_path: Path) -> SQLiteLiveExecutionJournal:
    journal = SQLiteLiveExecutionJournal(tmp_path / "katana.db", now_provider=lambda: NOW)
    journal.prepare("exec-1", order_fingerprint="fp", order_id="order-1", signal_id="signal-1")
    journal.claim("exec-1")
    journal.mark_submission_pending("exec-1")
    journal.mark_submitted("exec-1", broker_order_id=BROKER_ID)
    return journal


@pytest.mark.parametrize(
    ("broker_state", "expected"),
    [
        (LiveExecutionReconciliationState.ACCEPTED, LiveSubmittedExecutionDecision.WORKING),
        (LiveExecutionReconciliationState.PARTIALLY_FILLED, LiveSubmittedExecutionDecision.PARTIALLY_FILLED),
        (LiveExecutionReconciliationState.FILLED, LiveSubmittedExecutionDecision.FILLED),
        (LiveExecutionReconciliationState.TERMINATED_UNFILLED, LiveSubmittedExecutionDecision.TERMINATED_UNFILLED),
        (LiveExecutionReconciliationState.TERMINATED_PARTIAL, LiveSubmittedExecutionDecision.TERMINATED_PARTIAL),
        (LiveExecutionReconciliationState.UNKNOWN, LiveSubmittedExecutionDecision.UNKNOWN),
    ],
)
def test_submitted_execution_maps_broker_state_without_mutating_journal(tmp_path, broker_state, expected):
    journal = submitted_journal(tmp_path)
    before = journal.get_required("exec-1")
    reconciler = FakeReconciler(broker_state)
    lifecycle = LiveSubmittedExecutionLifecycle(journal=journal, reconciliation_service=reconciler)

    result = lifecycle.reconcile("exec-1")

    assert result.decision is expected
    assert result.may_retry_submission is False
    assert reconciler.calls == [BROKER_ID]
    assert journal.get_required("exec-1") == before


def test_filled_is_only_true_for_broker_confirmed_full_fill(tmp_path):
    journal = submitted_journal(tmp_path)
    lifecycle = LiveSubmittedExecutionLifecycle(
        journal=journal,
        reconciliation_service=FakeReconciler(LiveExecutionReconciliationState.FILLED),
    )
    assert lifecycle.reconcile("exec-1").is_fully_filled is True


def test_non_submitted_execution_cannot_be_reconciled(tmp_path):
    journal = SQLiteLiveExecutionJournal(tmp_path / "katana.db", now_provider=lambda: NOW)
    journal.prepare("exec-1", order_fingerprint="fp", order_id="order-1", signal_id="signal-1")
    lifecycle = LiveSubmittedExecutionLifecycle(
        journal=journal,
        reconciliation_service=FakeReconciler(LiveExecutionReconciliationState.FILLED),
    )
    with pytest.raises(LiveExecutionTransitionError):
        lifecycle.reconcile("exec-1")


def test_unknown_is_fail_closed_and_never_authorizes_resubmission(tmp_path):
    journal = submitted_journal(tmp_path)
    lifecycle = LiveSubmittedExecutionLifecycle(
        journal=journal,
        reconciliation_service=FakeReconciler(LiveExecutionReconciliationState.UNKNOWN),
    )
    result = lifecycle.reconcile("exec-1")
    assert result.decision is LiveSubmittedExecutionDecision.UNKNOWN
    assert result.may_retry_submission is False
