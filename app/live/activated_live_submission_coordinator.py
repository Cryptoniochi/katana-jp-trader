"""Phase 6-F activated live submission coordinator.

This module leaves the Phase 6-C locked coordinator unchanged.
It persists SUBMISSION_PENDING before transport. A confirmed OrderId becomes
SUBMITTED. Any exception after the transport call begins is frozen as UNKNOWN
and is never automatically retried.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import StrEnum

from app.live.activated_live_broker_transport import (
    ActivatedKabuStationLiveTransport,
    ActivatedLiveTransportDecision,
    ActivatedLiveTransportResult,
)
from app.live.live_broker_transport_models import LiveTransportRequest
from app.live.live_execution_journal_models import (
    LiveExecutionJournalRecord,
    LiveExecutionState,
)
from app.live.live_execution_journal_repository import (
    LiveExecutionTransitionError,
    SQLiteLiveExecutionJournal,
)
from app.live.live_order_adapter import LockedLiveOrderAdapter
from app.live.live_submission_boundary import LockedLiveSubmissionBoundary
from app.live.live_submission_boundary_models import LiveSubmissionBoundaryResult
from app.trading.order_models import TradeOrder


NowProvider = Callable[[], datetime]


class ActivatedLiveSubmissionDecision(StrEnum):
    TRANSPORT_BLOCKED = "transport_blocked"
    SUBMITTED = "submitted"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class ActivatedLiveSubmissionResult:
    decision: ActivatedLiveSubmissionDecision
    evaluated_at: datetime
    journal_record: LiveExecutionJournalRecord
    submission_boundary_result: LiveSubmissionBoundaryResult
    transport_result: ActivatedLiveTransportResult | None
    message: str

    def __post_init__(self) -> None:
        if self.evaluated_at.tzinfo is None:
            raise ValueError("evaluated_at must be timezone-aware.")
        if not self.message.strip():
            raise ValueError("message must not be empty.")


class ActivatedLiveSubmissionCoordinator:
    def __init__(
        self,
        *,
        journal: SQLiteLiveExecutionJournal,
        submission_boundary: LockedLiveSubmissionBoundary,
        transport: ActivatedKabuStationLiveTransport,
        now_provider: NowProvider | None = None,
    ) -> None:
        self.journal = journal
        self.submission_boundary = submission_boundary
        self.transport = transport
        self.now_provider = now_provider or (lambda: datetime.now(timezone.utc))

    def submit(
        self,
        *,
        execution_key: str,
        order: TradeOrder,
        trading_date: date,
    ) -> ActivatedLiveSubmissionResult:
        current = self.journal.get_required(execution_key)
        if current.state is not LiveExecutionState.CLAIMED:
            raise LiveExecutionTransitionError(
                "Only a CLAIMED live execution may enter activated submission."
            )

        if order.order_id != current.order_id or order.signal_id != current.signal_id:
            raise ValueError("TradeOrder identity does not match execution journal.")
        fingerprint = LockedLiveOrderAdapter.create_order_fingerprint(order)
        if fingerprint != current.order_fingerprint:
            raise ValueError("TradeOrder fingerprint does not match execution journal.")

        boundary_result = self.submission_boundary.enter_submission_pending(
            execution_key
        )
        pending = boundary_result.journal_record
        if pending.state is not LiveExecutionState.SUBMISSION_PENDING:
            raise LiveExecutionTransitionError(
                "Submission boundary did not persist SUBMISSION_PENDING."
            )

        request = LiveTransportRequest(
            execution_key=execution_key,
            order=order,
            requested_at=self._current_time(),
        )

        # Pre-network local locks are not ambiguous. Keep SUBMISSION_PENDING,
        # matching the Phase 6-C recovery contract.
        if not self.transport.activation_enabled or not self.transport.runtime_armed:
            result = self.transport.submit(request, trading_date=trading_date)
            return ActivatedLiveSubmissionResult(
                decision=ActivatedLiveSubmissionDecision.TRANSPORT_BLOCKED,
                evaluated_at=self._current_time(),
                journal_record=self.journal.get_required(execution_key),
                submission_boundary_result=boundary_result,
                transport_result=result,
                message="Live transport was locally blocked; no broker call occurred.",
            )

        # Daily arming authorization is also a local check. Evaluate it through
        # transport; if blocked, no network request occurred.
        try:
            result = self.transport.submit(request, trading_date=trading_date)
        except Exception as error:
            unknown = self.journal.mark_unknown(
                execution_key,
                detail=(
                    "Live broker submission outcome is ambiguous; automatic retry "
                    f"is prohibited. error={type(error).__name__}: {error}"
                ),
            )
            return ActivatedLiveSubmissionResult(
                decision=ActivatedLiveSubmissionDecision.UNKNOWN,
                evaluated_at=self._current_time(),
                journal_record=unknown,
                submission_boundary_result=boundary_result,
                transport_result=None,
                message=(
                    "Live broker submission raised after SUBMISSION_PENDING; "
                    "execution frozen as UNKNOWN."
                ),
            )

        if result.decision is ActivatedLiveTransportDecision.BLOCKED:
            return ActivatedLiveSubmissionResult(
                decision=ActivatedLiveSubmissionDecision.TRANSPORT_BLOCKED,
                evaluated_at=self._current_time(),
                journal_record=self.journal.get_required(execution_key),
                submission_boundary_result=boundary_result,
                transport_result=result,
                message="Live transport authorization blocked before broker submission.",
            )

        submitted = self.journal.mark_submitted(
            execution_key,
            broker_order_id=result.broker_order_id or "",
            detail="kabu Station returned a confirmed OrderId.",
        )
        return ActivatedLiveSubmissionResult(
            decision=ActivatedLiveSubmissionDecision.SUBMITTED,
            evaluated_at=self._current_time(),
            journal_record=submitted,
            submission_boundary_result=boundary_result,
            transport_result=result,
            message="Live execution is durably SUBMITTED.",
        )

    def _current_time(self) -> datetime:
        current = self.now_provider()
        if current.tzinfo is None:
            raise ValueError("now_provider must return a timezone-aware datetime.")
        return current.astimezone(timezone.utc)
