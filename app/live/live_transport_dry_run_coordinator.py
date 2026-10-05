"""Phase 6-D Step 6A dry-run submission coordinator.

The coordinator deliberately uses the existing durable submission boundary, but
must be used with a dedicated dry-run SQLite database.  It never marks an
execution SUBMITTED because no broker transmission occurs.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timezone

from app.live.live_broker_transport_models import LiveTransportRequest
from app.live.live_execution_journal_models import LiveExecutionState
from app.live.live_execution_journal_repository import (
    LiveExecutionTransitionError,
    SQLiteLiveExecutionJournal,
)
from app.live.live_order_adapter import LockedLiveOrderAdapter
from app.live.live_submission_boundary import LockedLiveSubmissionBoundary
from app.live.live_transport_dry_run import SimulatedLiveBrokerTransport
from app.live.live_transport_dry_run_models import (
    DryRunSubmissionDecision,
    DryRunSubmissionResult,
    SimulatedLiveTransportDecision,
)
from app.trading.order_models import TradeOrder


NowProvider = Callable[[], datetime]


class DryRunLiveSubmissionCoordinator:
    """Run CLAIMED -> SUBMISSION_PENDING -> simulated transport, without network."""

    def __init__(
        self,
        *,
        journal: SQLiteLiveExecutionJournal,
        submission_boundary: LockedLiveSubmissionBoundary,
        transport: SimulatedLiveBrokerTransport,
        now_provider: NowProvider | None = None,
    ) -> None:
        self.journal = journal
        self.submission_boundary = submission_boundary
        self.transport = transport
        self.now_provider = now_provider or (lambda: datetime.now(timezone.utc))

    def evaluate(
        self,
        *,
        execution_key: str,
        order: TradeOrder,
        trading_date: date,
    ) -> DryRunSubmissionResult:
        current = self.journal.get_required(execution_key)
        if current.state is not LiveExecutionState.CLAIMED:
            raise LiveExecutionTransitionError(
                "Only a CLAIMED execution may enter the dry-run submission path."
            )

        if order.order_id != current.order_id:
            raise ValueError("TradeOrder order_id does not match the execution journal.")
        if order.signal_id != current.signal_id:
            raise ValueError("TradeOrder signal_id does not match the execution journal.")

        candidate = LockedLiveOrderAdapter.create_order_fingerprint(order)
        if candidate != current.order_fingerprint:
            raise ValueError(
                "TradeOrder fingerprint does not match the execution journal."
            )

        boundary_result = self.submission_boundary.enter_submission_pending(
            execution_key
        )
        if boundary_result.journal_record.state is not LiveExecutionState.SUBMISSION_PENDING:
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
        if (
            transport_result.decision
            is not SimulatedLiveTransportDecision.SIMULATED_ACCEPTED
        ):
            raise RuntimeError("Dry-run transport returned an unsupported decision.")

        after_transport = self.journal.get_required(execution_key)
        if after_transport.state is not LiveExecutionState.SUBMISSION_PENDING:
            raise LiveExecutionTransitionError(
                "Dry-run transport unexpectedly changed durable execution state."
            )

        return DryRunSubmissionResult(
            decision=DryRunSubmissionDecision.SIMULATED_TRANSPORT_REACHED,
            evaluated_at=self._current_time(),
            journal_record=after_transport,
            submission_boundary_result=boundary_result,
            transport_result=transport_result,
            message=(
                "Dry-run reached the simulated transport and remains durably "
                "SUBMISSION_PENDING in the dedicated dry-run journal; no broker "
                "transmission occurred."
            ),
        )

    def _current_time(self) -> datetime:
        current = self.now_provider()
        if current.tzinfo is None:
            raise ValueError("now_provider must return a timezone-aware datetime.")
        return current.astimezone(timezone.utc)
