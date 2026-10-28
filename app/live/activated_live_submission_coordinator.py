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
import re

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
from app.market.kabu_station_models import KabuStationResponseError
from app.live.live_submission_boundary import LockedLiveSubmissionBoundary
from app.live.live_submission_boundary_models import LiveSubmissionBoundaryResult
from app.trading.order_models import TradeOrder


NowProvider = Callable[[], datetime]


class ActivatedLiveSubmissionDecision(StrEnum):
    TRANSPORT_BLOCKED = "transport_blocked"
    SUBMITTED = "submitted"
    UNKNOWN = "unknown"
    BROKER_REJECTED = "broker_rejected"


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
        except KabuStationResponseError as error:
            # A syntactically valid HTTP 4xx response with a kabu Station error
            # code proves that the broker/API rejected this request.  It is not
            # an ambiguous network outcome and must not poison later Live cycles.
            # Keep 5xx and malformed/2xx response failures fail-closed as UNKNOWN.
            if self._is_explicit_broker_rejection(error):
                rejected = self.journal.mark_broker_rejected(
                    execution_key,
                    detail=(
                        "kabu Station explicitly rejected the Live order; automatic "
                        f"retry is prohibited. error={type(error).__name__}: {error}"
                    ),
                )
                return ActivatedLiveSubmissionResult(
                    decision=ActivatedLiveSubmissionDecision.BROKER_REJECTED,
                    evaluated_at=self._current_time(),
                    journal_record=rejected,
                    submission_boundary_result=boundary_result,
                    transport_result=None,
                    message=(
                        "Live broker explicitly rejected the order; execution "
                        "closed without automatic retry."
                    ),
                )
            return self._freeze_unknown(
                execution_key=execution_key,
                boundary_result=boundary_result,
                error=error,
            )
        except Exception as error:
            return self._freeze_unknown(
                execution_key=execution_key,
                boundary_result=boundary_result,
                error=error,
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

    @staticmethod
    def _is_explicit_broker_rejection(error: KabuStationResponseError) -> bool:
        message = str(error)
        match = re.search(r"status=(\d+)\s+code=([^\s]+)", message)
        if match is None:
            return False
        status = int(match.group(1))
        code = match.group(2).strip()
        return 400 <= status < 500 and code not in {"None", "null", ""}

    def _freeze_unknown(
        self,
        *,
        execution_key: str,
        boundary_result: LiveSubmissionBoundaryResult,
        error: Exception,
    ) -> ActivatedLiveSubmissionResult:
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

    def _current_time(self) -> datetime:
        current = self.now_provider()
        if current.tzinfo is None:
            raise ValueError("now_provider must return a timezone-aware datetime.")
        return current.astimezone(timezone.utc)
