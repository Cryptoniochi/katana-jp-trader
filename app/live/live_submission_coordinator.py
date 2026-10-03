"""Phase 6-C Step 2 locked live submission coordinator.

Safety invariants:
- only a CLAIMED execution may start this path;
- the journal is durably SUBMISSION_PENDING before transport evaluation;
- the transport boundary remains locked and has no broker/network dependency;
- a LOCKED transport result is not an ambiguous broker outcome;
- therefore a locally locked attempt remains SUBMISSION_PENDING, not UNKNOWN;
- this coordinator cannot mark an execution SUBMITTED and cannot retry it.

A future transport implementation must introduce a separate, explicit unlock
phase.  This module deliberately provides no submission or network method.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timezone

from app.live.live_broker_transport import LockedLiveBrokerTransport
from app.live.live_broker_transport_models import (
    LiveTransportDecision,
    LiveTransportRequest,
)
from app.live.live_execution_journal_models import LiveExecutionState
from app.live.live_execution_journal_repository import (
    LiveExecutionTransitionError,
    SQLiteLiveExecutionJournal,
)
from app.live.live_submission_boundary import LockedLiveSubmissionBoundary
from app.live.live_submission_coordinator_models import (
    LiveSubmissionCoordinatorDecision,
    LiveSubmissionCoordinatorResult,
)
from app.trading.order_models import TradeOrder


NowProvider = Callable[[], datetime]


class LockedLiveSubmissionCoordinator:
    """Connect durable SUBMISSION_PENDING state to the locked transport."""

    def __init__(
        self,
        *,
        journal: SQLiteLiveExecutionJournal,
        submission_boundary: LockedLiveSubmissionBoundary,
        transport: LockedLiveBrokerTransport,
        now_provider: NowProvider | None = None,
    ) -> None:
        self.journal = journal
        self.submission_boundary = submission_boundary
        self.transport = transport
        self.now_provider = (
            now_provider
            if now_provider is not None
            else lambda: datetime.now(timezone.utc)
        )

    def evaluate(
        self,
        *,
        execution_key: str,
        order: TradeOrder,
        trading_date: date,
    ) -> LiveSubmissionCoordinatorResult:
        """Enter SUBMISSION_PENDING and stop at the locked transport."""

        current = self.journal.get_required(execution_key)
        if current.state is not LiveExecutionState.CLAIMED:
            raise LiveExecutionTransitionError(
                "Only a CLAIMED live execution may enter the locked "
                "submission coordinator."
            )

        self._validate_order_identity(
            current_order_id=current.order_id,
            current_signal_id=current.signal_id,
            order=order,
        )

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
        transport_result = self.transport.evaluate(
            request,
            trading_date=trading_date,
        )

        if transport_result.decision is not LiveTransportDecision.LOCKED:
            raise RuntimeError(
                "Phase 6-C locked transport returned an unsupported decision."
            )

        # Re-read durable state after transport evaluation.  A local LOCKED
        # result proves that no broker transmission was attempted, so this is
        # intentionally not converted to UNKNOWN.
        after_transport = self.journal.get_required(execution_key)
        if after_transport.state is not LiveExecutionState.SUBMISSION_PENDING:
            raise LiveExecutionTransitionError(
                "Locked transport evaluation changed the durable execution "
                "state unexpectedly."
            )

        return LiveSubmissionCoordinatorResult(
            decision=LiveSubmissionCoordinatorDecision.TRANSPORT_LOCKED,
            evaluated_at=self._current_time(),
            journal_record=after_transport,
            submission_boundary_result=boundary_result,
            transport_result=transport_result,
            message=(
                "Live execution remains durably SUBMISSION_PENDING because "
                "the broker transport is locked and no transmission occurred."
            ),
        )

    @staticmethod
    def _validate_order_identity(
        *,
        current_order_id: str,
        current_signal_id: str,
        order: TradeOrder,
    ) -> None:
        if order.order_id != current_order_id:
            raise ValueError(
                "TradeOrder order_id does not match the execution journal."
            )
        if order.signal_id != current_signal_id:
            raise ValueError(
                "TradeOrder signal_id does not match the execution journal."
            )

    def _current_time(self) -> datetime:
        current = self.now_provider()
        if current.tzinfo is None:
            raise ValueError("now_provider must return a timezone-aware datetime.")
        return current.astimezone(timezone.utc)
