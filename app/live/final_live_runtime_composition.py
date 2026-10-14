"""Final dedicated Live runtime composition.

Construction performs no broker reads and does not touch Paper/Shadow runtime.
All activation flags default to fail-closed.  The graph joins authoritative
kabu Station account state, live risk/safety preparation, durable claim and
submission, broker execution/position reconciliation, protective exits,
durable cancellation, and EOD liquidation.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.live.activated_live_broker_transport import ActivatedKabuStationLiveTransport
from app.live.activated_live_submission_coordinator import ActivatedLiveSubmissionCoordinator
from app.live.execution_mode import ExecutionModeSettings
from app.live.kabu_station_cash_order_sender import KabuStationCashOrderSender
from app.live.live_account_runtime_composition import (
    LiveAccountRuntimeProviderFactory,
    LiveAccountRuntimeProviders,
)
from app.live.live_cancel_journal_repository import SQLiteLiveCancelJournalRepository
from app.live.live_eod_liquidation_flow import LiveEodLiquidationFlow
from app.live.live_execution_position_consistency import LiveExecutionPositionConsistencyService
from app.live.live_execution_reconciliation import LiveExecutionReconciliationService
from app.live.live_execution_tracking_flow import (
    LiveExecutionTrackingFlow,
    SQLiteLivePositionBaselineRepository,
)
from app.live.live_exit_order_conflict_service import LiveExitOrderConflictService
from app.live.live_prepared_execution_tracking_flow import LivePreparedExecutionTrackingFlow
from app.live.live_protective_cancel_service import LiveProtectiveCancelService
from app.live.live_protective_exit_conflict_resolver import LiveProtectiveExitConflictResolver
from app.live.live_protective_exit_execution_flow import LiveProtectiveExitExecutionFlow
from app.live.live_protective_exit_service import LiveProtectiveExitService
from app.live.live_protective_stop_repository import SQLiteLiveProtectiveStopRepository
from app.live.live_protective_stop_cycle import LiveProtectiveStopCycle
from app.live.live_submitted_execution_lifecycle import LiveSubmittedExecutionLifecycle
from app.live.locked_live_runtime_composition import (
    LockedLiveRuntimeBundle,
    LockedLiveRuntimeFactory,
)
from app.live.live_daily_loss_state import DailyClosedTradeRepository
from app.live.live_order_safety import LiveOrderSafetySnapshot
from app.live.risk_manager import LiveRiskManager
from app.risk.kill_switch_models import KillSwitchSnapshot
from app.market.kabu_station_client import KabuStationClient

NowProvider = Callable[[], datetime]
MarketPriceProvider = Callable[[str], float]
SafetySnapshotProvider = Callable[[], LiveOrderSafetySnapshot]
KillSwitchSnapshotProvider = Callable[[], KillSwitchSnapshot]


@dataclass(frozen=True, slots=True)
class FinalLiveRuntimeBundle:
    account: LiveAccountRuntimeProviders
    foundation: LockedLiveRuntimeBundle
    transport: ActivatedKabuStationLiveTransport
    submission_coordinator: ActivatedLiveSubmissionCoordinator
    reconciliation_service: LiveExecutionReconciliationService
    submitted_lifecycle: LiveSubmittedExecutionLifecycle
    position_consistency_service: LiveExecutionPositionConsistencyService
    baseline_repository: SQLiteLivePositionBaselineRepository
    tracking_flow: LiveExecutionTrackingFlow
    prepared_tracking_flow: LivePreparedExecutionTrackingFlow
    protective_exit_service: LiveProtectiveExitService
    cancel_journal: SQLiteLiveCancelJournalRepository
    cancel_service: LiveProtectiveCancelService
    conflict_service: LiveExitOrderConflictService
    conflict_resolver: LiveProtectiveExitConflictResolver
    protective_exit_execution_flow: LiveProtectiveExitExecutionFlow
    protective_stop_repository: SQLiteLiveProtectiveStopRepository
    protective_stop_cycle: LiveProtectiveStopCycle
    eod_liquidation_flow: LiveEodLiquidationFlow


class FinalLiveRuntimeFactory:
    """Build the complete Live-only graph; defaults remain non-transmitting."""

    @staticmethod
    def create(
        *,
        database_path: Path,
        kabu_client: KabuStationClient,
        sender: KabuStationCashOrderSender,
        execution_settings: ExecutionModeSettings,
        daily_trade_repository: DailyClosedTradeRepository,
        kabu_station_report_path: Path,
        live_equity_peak_path: Path,
        risk_manager: LiveRiskManager,
        safety_snapshot_provider: SafetySnapshotProvider,
        kill_switch_snapshot_provider: KillSwitchSnapshotProvider,
        market_price_provider: MarketPriceProvider,
        activation_enabled: bool = False,
        runtime_armed: bool = False,
        now_provider: NowProvider | None = None,
    ) -> FinalLiveRuntimeBundle:
        db = Path(database_path)
        account = LiveAccountRuntimeProviderFactory.create(
            kabu_client=kabu_client,
            daily_trade_repository=daily_trade_repository,
            kabu_station_report_path=Path(kabu_station_report_path),
            live_equity_peak_path=Path(live_equity_peak_path),
            now_provider=now_provider,
        )

        # Reuse the proven locked boundary for final risk, safety, Kill Switch,
        # idempotency, PREPARED and CLAIMED state.  It remains runtime-disarmed;
        # broker transmission exists only in the separate activated transport.
        foundation = LockedLiveRuntimeFactory.create(
            database_path=db,
            risk_manager=risk_manager,
            portfolio_provider=account.risk_portfolio_provider,
            safety_snapshot_provider=safety_snapshot_provider,
            kill_switch_snapshot_provider=kill_switch_snapshot_provider,
            execution_settings=execution_settings,
            market_price_provider=market_price_provider,
            now_provider=now_provider,
        )

        transport = ActivatedKabuStationLiveTransport(
            sender=sender,
            execution_settings=execution_settings,
            activation_enabled=activation_enabled,
            runtime_armed=runtime_armed,
            now_provider=now_provider,
        )
        submission_coordinator = ActivatedLiveSubmissionCoordinator(
            journal=foundation.journal,
            submission_boundary=foundation.submission_boundary,
            transport=transport,
            now_provider=now_provider,
        )

        reconciliation_service = LiveExecutionReconciliationService(
            client=kabu_client,
            product=0,
        )
        submitted_lifecycle = LiveSubmittedExecutionLifecycle(
            journal=foundation.journal,
            reconciliation_service=reconciliation_service,
        )
        position_consistency_service = LiveExecutionPositionConsistencyService(
            account_state_service=account.account_state_service,
        )
        baseline_repository = SQLiteLivePositionBaselineRepository(db)
        tracking_flow = LiveExecutionTrackingFlow(
            baseline_repository=baseline_repository,
            position_consistency_service=position_consistency_service,
            submission_coordinator=submission_coordinator,
            submitted_lifecycle=submitted_lifecycle,
        )
        prepared_tracking_flow = LivePreparedExecutionTrackingFlow(
            preparation_service=foundation.preparation_service,
            claim_gate=foundation.claim_gate,
            tracking_flow=tracking_flow,
            now_provider=now_provider,
        )

        protective_exit_service = LiveProtectiveExitService(
            account_state_provider=account.account_state_service,
            market_price_provider=market_price_provider,
            now_provider=now_provider,
        )
        cancel_journal = SQLiteLiveCancelJournalRepository(db)
        cancel_service = LiveProtectiveCancelService(
            client=kabu_client,
            journal_repository=cancel_journal,
        )
        conflict_service = LiveExitOrderConflictService(order_reader=kabu_client)
        conflict_resolver = LiveProtectiveExitConflictResolver(
            conflict_service=conflict_service,
            cancel_service=cancel_service,
            exit_service=protective_exit_service,
        )
        protective_exit_execution_flow = LiveProtectiveExitExecutionFlow(
            exit_service=protective_exit_service,
            tracking_flow=prepared_tracking_flow,
            conflict_resolver=conflict_resolver,
        )
        protective_stop_repository = SQLiteLiveProtectiveStopRepository(
            db, now_provider=now_provider
        )
        protective_stop_cycle = LiveProtectiveStopCycle(
            repository=protective_stop_repository,
            execution_flow=protective_exit_execution_flow,
        )
        eod_liquidation_flow = LiveEodLiquidationFlow(
            exit_service=protective_exit_service,
            conflict_resolver=conflict_resolver,
            execution_flow=protective_exit_execution_flow,
        )

        return FinalLiveRuntimeBundle(
            account=account,
            foundation=foundation,
            transport=transport,
            submission_coordinator=submission_coordinator,
            reconciliation_service=reconciliation_service,
            submitted_lifecycle=submitted_lifecycle,
            position_consistency_service=position_consistency_service,
            baseline_repository=baseline_repository,
            tracking_flow=tracking_flow,
            prepared_tracking_flow=prepared_tracking_flow,
            protective_exit_service=protective_exit_service,
            cancel_journal=cancel_journal,
            cancel_service=cancel_service,
            conflict_service=conflict_service,
            conflict_resolver=conflict_resolver,
            protective_exit_execution_flow=protective_exit_execution_flow,
            protective_stop_repository=protective_stop_repository,
            protective_stop_cycle=protective_stop_cycle,
            eod_liquidation_flow=eod_liquidation_flow,
        )
