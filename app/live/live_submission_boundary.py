"""Phase 6-B durable submission boundary with no broker transport.

The boundary performs exactly two safety-critical state operations:

1. CLAIMED -> SUBMISSION_PENDING before any future transport call can exist.
2. SUBMISSION_PENDING -> UNKNOWN when a previously pending execution is found
   during recovery, because the system cannot prove whether a future broker
   request was accepted before a crash or timeout.

UNKNOWN is deliberately frozen by the journal.  This service never retries,
submits, sends, or communicates with a broker.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

from app.live.live_execution_journal_models import LiveExecutionState
from app.live.live_execution_journal_repository import (
    LiveExecutionTransitionError,
    SQLiteLiveExecutionJournal,
)
from app.live.live_submission_boundary_models import (
    LiveSubmissionBoundaryDecision,
    LiveSubmissionBoundaryResult,
)


NowProvider = Callable[[], datetime]


class LockedLiveSubmissionBoundary:
    """Manage durable pre-transport state without providing transport."""

    def __init__(
        self,
        *,
        journal: SQLiteLiveExecutionJournal,
        now_provider: NowProvider | None = None,
    ) -> None:
        self.journal = journal
        self.now_provider = (
            now_provider
            if now_provider is not None
            else lambda: datetime.now(timezone.utc)
        )

    def enter_submission_pending(
        self,
        execution_key: str,
    ) -> LiveSubmissionBoundaryResult:
        """Atomically mark a CLAIMED execution pending; do not transmit it."""

        evaluated_at = self._current_time()
        current = self.journal.get_required(execution_key)

        if current.state is not LiveExecutionState.CLAIMED:
            raise LiveExecutionTransitionError(
                "Only a CLAIMED live execution may enter "
                "SUBMISSION_PENDING."
            )

        pending = self.journal.mark_submission_pending(execution_key)
        return LiveSubmissionBoundaryResult(
            decision=LiveSubmissionBoundaryDecision.SUBMISSION_PENDING,
            evaluated_at=evaluated_at,
            journal_record=pending,
            message=(
                "Live execution is durably SUBMISSION_PENDING; "
                "broker transmission remains unavailable."
            ),
        )

    def freeze_pending_as_unknown(
        self,
        execution_key: str,
        *,
        detail: str = (
            "Recovered SUBMISSION_PENDING execution has an ambiguous "
            "submission outcome and must be reconciled before any retry."
        ),
    ) -> LiveSubmissionBoundaryResult:
        """Freeze one recovered pending execution instead of retrying it."""

        evaluated_at = self._current_time()
        current = self.journal.get_required(execution_key)

        if current.state is not LiveExecutionState.SUBMISSION_PENDING:
            raise LiveExecutionTransitionError(
                "Only a SUBMISSION_PENDING live execution may be frozen "
                "as UNKNOWN."
            )

        unknown = self.journal.mark_unknown(
            execution_key,
            detail=detail,
        )
        return LiveSubmissionBoundaryResult(
            decision=LiveSubmissionBoundaryDecision.UNKNOWN,
            evaluated_at=evaluated_at,
            journal_record=unknown,
            message=(
                "Ambiguous live execution frozen as UNKNOWN; "
                "automatic retry is prohibited."
            ),
        )

    def recover_if_ambiguous(
        self,
        execution_key: str,
    ) -> LiveSubmissionBoundaryResult | None:
        """Freeze a recovered pending attempt; leave all other states alone."""

        current = self.journal.get_required(execution_key)
        if current.state is not LiveExecutionState.SUBMISSION_PENDING:
            return None
        return self.freeze_pending_as_unknown(execution_key)

    def _current_time(self) -> datetime:
        current = self.now_provider()
        if current.tzinfo is None:
            raise ValueError("now_provider must return a timezone-aware datetime.")
        return current.astimezone(timezone.utc)
