from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.live.live_execution_journal_models import LiveExecutionState
from app.live.live_execution_journal_repository import (
    LiveExecutionJournalConflictError,
    SQLiteLiveExecutionJournal,
)
from app.live.live_execution_preparation_service import (
    LockedLiveExecutionPreparationService,
)
from app.live.live_order_adapter import LockedLiveOrderAdapter
from app.live.live_order_models import LiveOrderDecision, LiveOrderIntent
from app.trading.order_models import OrderSide, OrderType, TradeOrder


NOW = datetime(2026, 10, 3, 1, 23, 45, tzinfo=timezone.utc)


class BoundaryStub:
    def __init__(self, decision):
        self.decision = decision
        self.calls = 0

    def evaluate(self, intent):
        self.calls += 1
        return SimpleNamespace(
            intent=intent,
            decision=self.decision,
        )


def _order(*, order_id="order-1", signal_id="signal-1", quantity=100):
    return TradeOrder(
        order_id=order_id,
        signal_id=signal_id,
        code="7203",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=quantity,
        limit_price=1000.0,
        stop_price=None,
    )


def _intent(order=None):
    resolved = _order() if order is None else order
    return LiveOrderIntent(
        order=resolved,
        idempotency_key=LockedLiveOrderAdapter.create_idempotency_key(resolved),
        created_at=NOW,
    )


def _journal(tmp_path):
    return SQLiteLiveExecutionJournal(
        tmp_path / "katana.db",
        now_provider=lambda: NOW,
    )


def test_locked_boundary_converges_to_prepared(tmp_path):
    boundary = BoundaryStub(LiveOrderDecision.LOCKED)
    journal = _journal(tmp_path)
    service = LockedLiveExecutionPreparationService(
        boundary=boundary,
        journal=journal,
    )
    intent = _intent()

    result = service.prepare(intent)

    assert boundary.calls == 1
    assert result.newly_prepared is True
    assert result.is_prepared is True
    assert result.journal_record is not None
    assert result.journal_record.execution_key == intent.idempotency_key
    assert result.journal_record.state is LiveExecutionState.PREPARED
    assert journal.count() == 1


def test_blocked_boundary_never_creates_journal_record(tmp_path):
    boundary = BoundaryStub(LiveOrderDecision.BLOCKED)
    journal = _journal(tmp_path)
    service = LockedLiveExecutionPreparationService(
        boundary=boundary,
        journal=journal,
    )

    result = service.prepare(_intent())

    assert result.journal_record is None
    assert result.newly_prepared is False
    assert result.is_prepared is False
    assert journal.count() == 0


def test_duplicate_repairs_reservation_to_journal_crash_window(tmp_path):
    boundary = BoundaryStub(LiveOrderDecision.DUPLICATE)
    journal = _journal(tmp_path)
    service = LockedLiveExecutionPreparationService(
        boundary=boundary,
        journal=journal,
    )
    intent = _intent()

    # Simulates restart after Phase 6-A idempotency reservation committed,
    # but before the Phase 6-B PREPARED journal row was created.
    assert journal.get(intent.idempotency_key) is None

    result = service.prepare(intent)

    assert result.newly_prepared is True
    assert result.is_prepared is True
    assert journal.count() == 1


def test_repeated_preparation_is_idempotent_and_does_not_claim(tmp_path):
    journal = _journal(tmp_path)
    intent = _intent()

    first_service = LockedLiveExecutionPreparationService(
        boundary=BoundaryStub(LiveOrderDecision.LOCKED),
        journal=journal,
    )
    first = first_service.prepare(intent)
    assert first.newly_prepared is True

    retry_service = LockedLiveExecutionPreparationService(
        boundary=BoundaryStub(LiveOrderDecision.DUPLICATE),
        journal=journal,
    )
    retry = retry_service.prepare(intent)

    assert retry.newly_prepared is False
    assert retry.is_prepared is True
    assert retry.journal_record is not None
    assert retry.journal_record.state is LiveExecutionState.PREPARED
    assert journal.count() == 1


def test_existing_key_with_different_immutable_content_is_rejected(tmp_path):
    journal = _journal(tmp_path)
    intent = _intent()
    journal.prepare(
        execution_key=intent.idempotency_key,
        order_fingerprint="different-fingerprint",
        order_id=intent.order.order_id,
        signal_id=intent.order.signal_id,
    )
    service = LockedLiveExecutionPreparationService(
        boundary=BoundaryStub(LiveOrderDecision.DUPLICATE),
        journal=journal,
    )

    with pytest.raises(LiveExecutionJournalConflictError):
        service.prepare(intent)


def test_preparation_service_exposes_no_claim_or_send_operation(tmp_path):
    service = LockedLiveExecutionPreparationService(
        boundary=BoundaryStub(LiveOrderDecision.LOCKED),
        journal=_journal(tmp_path),
    )

    assert not hasattr(service, "claim")
    assert not hasattr(service, "submit")
    assert not hasattr(service, "submit_order")
    assert not hasattr(service, "send_order")
    assert not hasattr(service, "sendorder")
    assert not hasattr(service, "transmit")
