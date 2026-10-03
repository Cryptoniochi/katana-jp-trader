"""Phase 6-C Step 4A isolated composition for locked live execution.

This composition is deliberately separate from the Paper Trading runtime.

Safety invariants:
- constructing this bundle does not modify or wrap the Paper runtime;
- emergency safety and Kill Switch providers are mandatory;
- the live order adapter remains runtime-disarmed;
- the broker transport remains runtime-disarmed;
- the broker transport has no BrokerAdapter, HTTP client, or order endpoint;
- no component in this composition can mark an execution SUBMITTED by itself.

Step 4A only proves that the already-tested locked live components can be
assembled consistently around the same durable SQLite database.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.live.execution_mode import ExecutionModeSettings
from app.live.live_broker_transport import LockedLiveBrokerTransport
from app.live.live_execution_claim_gate import LiveExecutionClaimGate
from app.live.live_execution_journal_repository import (
    SQLiteLiveExecutionJournal,
)
from app.live.live_execution_preparation_service import (
    LockedLiveExecutionPreparationService,
)
from app.live.live_order_adapter import LockedLiveOrderAdapter
from app.live.live_order_idempotency_repository import (
    SQLiteLiveOrderIdempotencyStore,
)
from app.live.live_order_safety import LiveOrderSafetySnapshot
from app.live.live_submission_boundary import LockedLiveSubmissionBoundary
from app.live.live_submission_coordinator import LockedLiveSubmissionCoordinator
from app.live.risk_manager import LiveRiskManager
from app.live.risk_models import RiskPortfolioSnapshot
from app.risk.kill_switch_models import KillSwitchSnapshot
from app.risk.kill_switch_service import KillSwitchService


NowProvider = Callable[[], datetime]
PortfolioProvider = Callable[[], RiskPortfolioSnapshot]
SafetySnapshotProvider = Callable[[], LiveOrderSafetySnapshot]
KillSwitchSnapshotProvider = Callable[[], KillSwitchSnapshot]
MarketPriceProvider = Callable[[str], float]


@dataclass(frozen=True, slots=True)
class LockedLiveRuntimeBundle:
    """Fully assembled but non-transmitting live execution foundation."""

    idempotency_store: SQLiteLiveOrderIdempotencyStore
    journal: SQLiteLiveExecutionJournal
    order_adapter: LockedLiveOrderAdapter
    preparation_service: LockedLiveExecutionPreparationService
    claim_gate: LiveExecutionClaimGate
    submission_boundary: LockedLiveSubmissionBoundary
    transport: LockedLiveBrokerTransport
    submission_coordinator: LockedLiveSubmissionCoordinator


class LockedLiveRuntimeFactory:
    """Build an isolated locked-live component graph.

    No Paper Trading object is accepted by this factory.  That separation is
    intentional in Step 4A: creating the live foundation must not change the
    existing production Paper runtime path.
    """

    @staticmethod
    def create(
        *,
        database_path: Path,
        risk_manager: LiveRiskManager,
        portfolio_provider: PortfolioProvider,
        safety_snapshot_provider: SafetySnapshotProvider,
        kill_switch_snapshot_provider: KillSwitchSnapshotProvider,
        execution_settings: ExecutionModeSettings | None = None,
        market_price_provider: MarketPriceProvider | None = None,
        now_provider: NowProvider | None = None,
    ) -> LockedLiveRuntimeBundle:
        resolved_database_path = Path(database_path)
        resolved_execution_settings = (
            execution_settings
            if execution_settings is not None
            else ExecutionModeSettings()
        )

        kill_switch_service = KillSwitchService()

        idempotency_store = SQLiteLiveOrderIdempotencyStore(
            resolved_database_path,
            now_provider=now_provider,
        )
        journal = SQLiteLiveExecutionJournal(
            resolved_database_path,
            now_provider=now_provider,
        )

        order_adapter = LockedLiveOrderAdapter(
            risk_manager=risk_manager,
            kill_switch_service=kill_switch_service,
            portfolio_provider=portfolio_provider,
            kill_switch_snapshot_provider=kill_switch_snapshot_provider,
            idempotency_store=idempotency_store,
            safety_snapshot_provider=safety_snapshot_provider,
            market_price_provider=market_price_provider,
            runtime_armed=False,
            now_provider=now_provider,
        )

        preparation_service = LockedLiveExecutionPreparationService(
            boundary=order_adapter,
            journal=journal,
        )

        claim_gate = LiveExecutionClaimGate(
            journal=journal,
            kill_switch_service=kill_switch_service,
            safety_snapshot_provider=safety_snapshot_provider,
            kill_switch_snapshot_provider=kill_switch_snapshot_provider,
            now_provider=now_provider,
        )

        submission_boundary = LockedLiveSubmissionBoundary(
            journal=journal,
            now_provider=now_provider,
        )

        transport = LockedLiveBrokerTransport(
            execution_settings=resolved_execution_settings,
            runtime_armed=False,
            now_provider=now_provider,
        )

        submission_coordinator = LockedLiveSubmissionCoordinator(
            journal=journal,
            submission_boundary=submission_boundary,
            transport=transport,
            now_provider=now_provider,
        )

        return LockedLiveRuntimeBundle(
            idempotency_store=idempotency_store,
            journal=journal,
            order_adapter=order_adapter,
            preparation_service=preparation_service,
            claim_gate=claim_gate,
            submission_boundary=submission_boundary,
            transport=transport,
            submission_coordinator=submission_coordinator,
        )
