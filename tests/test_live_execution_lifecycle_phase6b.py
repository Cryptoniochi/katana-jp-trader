"""Phase 6-B end-to-end safety lifecycle tests.

These tests connect the locked Phase 6-A boundary to the durable Phase 6-B
preparation, claim, and submission-boundary components.  No broker transport
is used or expected anywhere in this lifecycle.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.live.live_execution_claim_gate import LiveExecutionClaimGate
from app.live.live_execution_journal_models import LiveExecutionState
from app.live.live_execution_journal_repository import (
    LiveExecutionAlreadyClaimedError,
    LiveExecutionTransitionError,
    SQLiteLiveExecutionJournal,
)
from app.live.live_execution_preparation_service import (
    LockedLiveExecutionPreparationService,
)
from app.live.live_order_adapter import LockedLiveOrderAdapter
from app.live.live_order_models import (
    LiveOrderDecision,
    LiveOrderIntent,
)
from app.live.live_order_safety import LiveOrderSafetySnapshot
from app.live.live_submission_boundary import LockedLiveSubmissionBoundary
from app.risk.kill_switch_models import KillSwitchSnapshot
from app.risk.kill_switch_service import KillSwitchService
from app.trading.order_models import OrderSide, OrderType, TradeOrder


NOW = datetime(2026, 10, 3, 4, 0, 0, tzinfo=timezone.utc)


@dataclass
class BoundarySequence:
    """Deterministic boundary result sequence for lifecycle integration tests."""

    decisions: list[LiveOrderDecision]

    def evaluate(self, intent: LiveOrderIntent):
        if not self.decisions:
            raise AssertionError("No boundary decision left for test.")
        return SimpleNamespace(
            intent=intent,
            decision=self.decisions.pop(0),
        )


def _order() -> TradeOrder:
    return TradeOrder(
        order_id="order-phase6b-step5",
        signal_id="signal-phase6b-step5",
        code="7203",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=100,
        limit_price=2500.0,
    )


def _intent() -> LiveOrderIntent:
    order = _order()
    return LiveOrderIntent(
        order=order,
        idempotency_key=LockedLiveOrderAdapter.create_idempotency_key(order),
        created_at=NOW,
    )


def _journal(path) -> SQLiteLiveExecutionJournal:
    return SQLiteLiveExecutionJournal(
        path,
        now_provider=lambda: NOW,
    )


def _healthy_safety() -> LiveOrderSafetySnapshot:
    return LiveOrderSafetySnapshot(
        safe_stop_active=False,
        reconciliation_consistent=True,
        reconciliation_state="consistent",
        evaluated_at=NOW,
    )


def _healthy_kill_switch() -> KillSwitchSnapshot:
    return KillSwitchSnapshot(
        manual_blocked=False,
        daily_loss_blocked=False,
        consecutive_loss_blocked=False,
        runtime_health_ok=True,
        heartbeat_alive=True,
        broker_available=True,
        evaluated_at=NOW,
    )


def _claim_gate(
    journal,
    *,
    safety_provider=_healthy_safety,
    kill_provider=_healthy_kill_switch,
):
    return LiveExecutionClaimGate(
        journal=journal,
        kill_switch_service=KillSwitchService(),
        safety_snapshot_provider=safety_provider,
        kill_switch_snapshot_provider=kill_provider,
        now_provider=lambda: NOW,
    )


def test_full_locked_lifecycle_reaches_pending_then_recovery_freezes_unknown(
    tmp_path,
):
    """LOCKED -> PREPARED -> CLAIMED -> PENDING -> restart -> UNKNOWN."""

    path = tmp_path / "katana.db"
    journal = _journal(path)
    intent = _intent()

    preparation = LockedLiveExecutionPreparationService(
        boundary=BoundarySequence([LiveOrderDecision.LOCKED]),
        journal=journal,
    )
    prepared = preparation.prepare(intent)

    assert prepared.is_prepared is True
    assert prepared.journal_record is not None
    assert prepared.journal_record.state is LiveExecutionState.PREPARED

    claimed = _claim_gate(journal).claim(intent.idempotency_key)
    assert claimed.is_claimed is True
    assert claimed.journal_record.state is LiveExecutionState.CLAIMED

    submission = LockedLiveSubmissionBoundary(
        journal=journal,
        now_provider=lambda: NOW,
    )
    pending = submission.enter_submission_pending(intent.idempotency_key)
    assert pending.is_submission_pending is True
    assert pending.journal_record.state is LiveExecutionState.SUBMISSION_PENDING

    reopened = _journal(path)
    recovery = LockedLiveSubmissionBoundary(
        journal=reopened,
        now_provider=lambda: NOW,
    )
    unknown = recovery.recover_if_ambiguous(intent.idempotency_key)

    assert unknown is not None
    assert unknown.is_unknown is True
    assert reopened.get_required(intent.idempotency_key).state is (
        LiveExecutionState.UNKNOWN
    )

    with pytest.raises(LiveExecutionAlreadyClaimedError):
        _claim_gate(reopened).claim(intent.idempotency_key)

    with pytest.raises(LiveExecutionTransitionError):
        recovery.enter_submission_pending(intent.idempotency_key)


def test_duplicate_boundary_result_repairs_prepare_gap_without_duplicate_row(
    tmp_path,
):
    """A durable Phase 6-A duplicate can converge to one PREPARED journal row."""

    path = tmp_path / "katana.db"
    journal = _journal(path)
    intent = _intent()

    preparation = LockedLiveExecutionPreparationService(
        boundary=BoundarySequence([LiveOrderDecision.DUPLICATE]),
        journal=journal,
    )
    result = preparation.prepare(intent)

    assert result.is_prepared is True
    assert result.newly_prepared is True
    assert journal.count() == 1
    assert journal.get_required(intent.idempotency_key).state is (
        LiveExecutionState.PREPARED
    )


def test_repeated_locked_then_duplicate_never_creates_second_execution(
    tmp_path,
):
    journal = _journal(tmp_path / "katana.db")
    intent = _intent()
    boundary = BoundarySequence(
        [
            LiveOrderDecision.LOCKED,
            LiveOrderDecision.DUPLICATE,
        ]
    )
    preparation = LockedLiveExecutionPreparationService(
        boundary=boundary,
        journal=journal,
    )

    first = preparation.prepare(intent)
    second = preparation.prepare(intent)

    assert first.newly_prepared is True
    assert second.newly_prepared is False
    assert journal.count() == 1
    assert journal.get_required(intent.idempotency_key).state is (
        LiveExecutionState.PREPARED
    )


def test_safe_stop_interrupts_lifecycle_before_claim(tmp_path):
    journal = _journal(tmp_path / "katana.db")
    intent = _intent()

    LockedLiveExecutionPreparationService(
        boundary=BoundarySequence([LiveOrderDecision.LOCKED]),
        journal=journal,
    ).prepare(intent)

    blocked = _claim_gate(
        journal,
        safety_provider=lambda: LiveOrderSafetySnapshot(
            safe_stop_active=True,
            reconciliation_consistent=True,
            reconciliation_state="consistent",
            evaluated_at=NOW,
        ),
    ).claim(intent.idempotency_key)

    assert blocked.is_blocked is True
    assert journal.get_required(intent.idempotency_key).state is (
        LiveExecutionState.PREPARED
    )


def test_reconciliation_failure_interrupts_lifecycle_before_claim(tmp_path):
    journal = _journal(tmp_path / "katana.db")
    intent = _intent()

    LockedLiveExecutionPreparationService(
        boundary=BoundarySequence([LiveOrderDecision.LOCKED]),
        journal=journal,
    ).prepare(intent)

    blocked = _claim_gate(
        journal,
        safety_provider=lambda: LiveOrderSafetySnapshot(
            safe_stop_active=False,
            reconciliation_consistent=False,
            reconciliation_state="mismatch",
            evaluated_at=NOW,
        ),
    ).claim(intent.idempotency_key)

    assert blocked.is_blocked is True
    assert journal.get_required(intent.idempotency_key).state is (
        LiveExecutionState.PREPARED
    )


def test_kill_switch_interrupts_lifecycle_before_claim(tmp_path):
    journal = _journal(tmp_path / "katana.db")
    intent = _intent()

    LockedLiveExecutionPreparationService(
        boundary=BoundarySequence([LiveOrderDecision.LOCKED]),
        journal=journal,
    ).prepare(intent)

    blocked = _claim_gate(
        journal,
        kill_provider=lambda: KillSwitchSnapshot(
            manual_blocked=True,
            daily_loss_blocked=False,
            consecutive_loss_blocked=False,
            runtime_health_ok=True,
            heartbeat_alive=True,
            broker_available=True,
            evaluated_at=NOW,
        ),
    ).claim(intent.idempotency_key)

    assert blocked.is_blocked is True
    assert journal.get_required(intent.idempotency_key).state is (
        LiveExecutionState.PREPARED
    )


def test_missing_runtime_safety_state_interrupts_lifecycle(tmp_path):
    journal = _journal(tmp_path / "katana.db")
    intent = _intent()

    LockedLiveExecutionPreparationService(
        boundary=BoundarySequence([LiveOrderDecision.LOCKED]),
        journal=journal,
    ).prepare(intent)

    blocked = _claim_gate(
        journal,
        safety_provider=None,
    ).claim(intent.idempotency_key)

    assert blocked.is_blocked is True
    assert journal.get_required(intent.idempotency_key).state is (
        LiveExecutionState.PREPARED
    )


def test_phase6b_lifecycle_components_expose_no_transport_api(tmp_path):
    journal = _journal(tmp_path / "katana.db")

    preparation = LockedLiveExecutionPreparationService(
        boundary=BoundarySequence([LiveOrderDecision.LOCKED]),
        journal=journal,
    )
    claim_gate = _claim_gate(journal)
    submission = LockedLiveSubmissionBoundary(
        journal=journal,
        now_provider=lambda: NOW,
    )

    forbidden = (
        "submit",
        "submit_order",
        "send_order",
        "sendorder",
        "transmit",
        "broker",
    )

    for component in (preparation, claim_gate, submission):
        for name in forbidden:
            assert not hasattr(component, name)
