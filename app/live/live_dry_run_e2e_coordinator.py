"""Phase 6-D Step 6B end-to-end Live dry-run coordinator.

Flow:
Final Live Readiness -> locked preparation -> fresh claim gate ->
durable SUBMISSION_PENDING -> simulated transport.

Safety invariants:
- Final Live Readiness must be activation-ready before journal preparation.
- The normal locked Phase 6-A boundary still performs safety/risk/idempotency.
- The claim gate re-reads emergency safety and Kill Switch state.
- The existing durable submission boundary is used.
- The final transport is SimulatedLiveBrokerTransport only.
- The dry-run journal remains SUBMISSION_PENDING after simulated acceptance.
- This coordinator contains no broker client, network operation, or SUBMITTED
  transition.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timezone

from app.live.execution_mode import ExecutionModeSettings
from app.live.final_live_readiness import FinalLiveReadinessGate
from app.live.live_dry_run_e2e_models import (
    LiveDryRunE2EDecision,
    LiveDryRunE2EResult,
)
from app.live.live_execution_claim_gate import LiveExecutionClaimGate
from app.live.live_execution_preparation_service import (
    LockedLiveExecutionPreparationService,
)
from app.live.live_order_models import LiveOrderIntent
from app.live.live_transport_dry_run_coordinator import (
    DryRunLiveSubmissionCoordinator,
)


NowProvider = Callable[[], datetime]


class LiveDryRunE2ECoordinator:
    """Rehearse the complete validated Live path without broker transmission."""

    def __init__(
        self,
        *,
        readiness_gate: FinalLiveReadinessGate,
        preparation_service: LockedLiveExecutionPreparationService,
        claim_gate: LiveExecutionClaimGate,
        submission_coordinator: DryRunLiveSubmissionCoordinator,
        execution_settings: ExecutionModeSettings,
        now_provider: NowProvider | None = None,
    ) -> None:
        self.readiness_gate = readiness_gate
        self.preparation_service = preparation_service
        self.claim_gate = claim_gate
        self.submission_coordinator = submission_coordinator
        self.execution_settings = execution_settings
        self.now_provider = now_provider or (lambda: datetime.now(timezone.utc))

    def run(
        self,
        *,
        intent: LiveOrderIntent,
        trading_date: date,
    ) -> LiveDryRunE2EResult:
        """Run one fail-closed, network-free end-to-end dry-run."""

        readiness = self.readiness_gate.check(
            execution_settings=self.execution_settings,
            trading_date=trading_date,
        )
        if not readiness.activation_ready:
            return LiveDryRunE2EResult(
                decision=LiveDryRunE2EDecision.BLOCKED_READINESS,
                evaluated_at=self._current_time(),
                readiness_report=readiness,
                preparation_result=None,
                claim_result=None,
                submission_result=None,
                message=(
                    "End-to-end Live dry-run blocked by Final Live Readiness "
                    "before durable execution preparation."
                ),
            )

        preparation = self.preparation_service.prepare(intent)
        if not preparation.is_prepared:
            return LiveDryRunE2EResult(
                decision=LiveDryRunE2EDecision.BLOCKED_PREPARATION,
                evaluated_at=self._current_time(),
                readiness_report=readiness,
                preparation_result=preparation,
                claim_result=None,
                submission_result=None,
                message=(
                    "End-to-end Live dry-run stopped at the locked order "
                    "preparation boundary."
                ),
            )

        claim = self.claim_gate.claim(intent.idempotency_key)
        if not claim.is_claimed:
            return LiveDryRunE2EResult(
                decision=LiveDryRunE2EDecision.BLOCKED_CLAIM,
                evaluated_at=self._current_time(),
                readiness_report=readiness,
                preparation_result=preparation,
                claim_result=claim,
                submission_result=None,
                message=(
                    "End-to-end Live dry-run stopped by the fresh execution "
                    "claim safety gate."
                ),
            )

        submission = self.submission_coordinator.evaluate(
            execution_key=intent.idempotency_key,
            order=intent.order,
            trading_date=trading_date,
        )
        return LiveDryRunE2EResult(
            decision=LiveDryRunE2EDecision.SIMULATED_TRANSPORT_REACHED,
            evaluated_at=self._current_time(),
            readiness_report=readiness,
            preparation_result=preparation,
            claim_result=claim,
            submission_result=submission,
            message=(
                "End-to-end Live dry-run reached simulated transport. "
                "No broker or network operation occurred."
            ),
        )

    def _current_time(self) -> datetime:
        current = self.now_provider()
        if current.tzinfo is None:
            raise ValueError("now_provider must return a timezone-aware datetime.")
        return current.astimezone(timezone.utc)
