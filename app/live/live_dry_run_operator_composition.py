from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Callable

from app.live.execution_mode import ExecutionModeSettings, TradingExecutionMode
from app.live.final_live_readiness import FinalLiveReadinessGate
from app.live.live_dry_run_e2e_coordinator import LiveDryRunE2ECoordinator
from app.live.live_dry_run_operational_service import LiveDryRunOperationalService
from app.live.live_order_models import LiveOrderIntent
from app.live.live_transport_dry_run import SimulatedLiveBrokerTransport
from app.live.live_transport_dry_run_coordinator import DryRunLiveSubmissionCoordinator
from app.live.locked_live_runtime_composition import LockedLiveRuntimeFactory
from app.live.risk_manager import LiveRiskManager
from app.trading.order_models import TradeOrder

NowProvider = Callable[[], datetime]


@dataclass(frozen=True, slots=True)
class LiveDryRunOperatorPaths:
    database_path: Path = Path("data/live_dry_run.db")
    report_path: Path = Path("reports/live/live_dry_run_audit.json")

    def __post_init__(self) -> None:
        if Path(self.database_path) == Path("data/katana.db"):
            raise ValueError("Dry-run database must not be the production Paper database.")


@dataclass(frozen=True, slots=True)
class LiveDryRunOperatorBundle:
    service: LiveDryRunOperationalService
    order_adapter: object
    paths: LiveDryRunOperatorPaths

    def create_intent(self, order: TradeOrder) -> LiveOrderIntent:
        return self.order_adapter.create_intent(order)


class LiveDryRunOperatorComposition:
    """Compose audited operator dry-run without enabling real Live transport."""

    @staticmethod
    def create(
        *,
        trading_date: date,
        live_confirmation: str,
        portfolio_provider,
        safety_snapshot_provider,
        kill_switch_snapshot_provider,
        manual_blocked_provider,
        daily_profit_loss_provider,
        consecutive_loss_count_provider,
        runtime_health_ok_provider,
        heartbeat_alive_provider,
        broker_available_provider,
        paths: LiveDryRunOperatorPaths | None = None,
        risk_manager: LiveRiskManager | None = None,
        market_price_provider=None,
        max_daily_loss: float = 50_000.0,
        max_consecutive_losses: int = 3,
        now_provider: NowProvider | None = None,
    ) -> LiveDryRunOperatorBundle:
        del trading_date  # authorization is revalidated by readiness/transport at run time
        resolved_paths = paths or LiveDryRunOperatorPaths()
        if Path(resolved_paths.database_path) == Path("data/katana.db"):
            raise ValueError("Dry-run database must be isolated from data/katana.db.")

        execution_settings = ExecutionModeSettings(
            mode=TradingExecutionMode.LIVE,
            live_armed=True,
            live_confirmation=live_confirmation,
        )
        readiness_gate = FinalLiveReadinessGate(
            manual_blocked_provider=manual_blocked_provider,
            daily_profit_loss_provider=daily_profit_loss_provider,
            consecutive_loss_count_provider=consecutive_loss_count_provider,
            runtime_health_ok_provider=runtime_health_ok_provider,
            heartbeat_alive_provider=heartbeat_alive_provider,
            broker_available_provider=broker_available_provider,
            portfolio_provider=portfolio_provider,
            safety_snapshot_provider=safety_snapshot_provider,
            kill_switch_snapshot_provider=kill_switch_snapshot_provider,
            max_daily_loss=max_daily_loss,
            max_consecutive_losses=max_consecutive_losses,
            now_provider=now_provider,
        )
        locked = LockedLiveRuntimeFactory.create(
            database_path=resolved_paths.database_path,
            risk_manager=risk_manager or LiveRiskManager(),
            portfolio_provider=portfolio_provider,
            safety_snapshot_provider=safety_snapshot_provider,
            kill_switch_snapshot_provider=kill_switch_snapshot_provider,
            execution_settings=execution_settings,
            market_price_provider=market_price_provider,
            now_provider=now_provider,
        )
        simulated_transport = SimulatedLiveBrokerTransport(
            execution_settings=execution_settings,
            now_provider=now_provider,
        )
        dry_submission = DryRunLiveSubmissionCoordinator(
            journal=locked.journal,
            submission_boundary=locked.submission_boundary,
            transport=simulated_transport,
            now_provider=now_provider,
        )
        e2e = LiveDryRunE2ECoordinator(
            readiness_gate=readiness_gate,
            preparation_service=locked.preparation_service,
            claim_gate=locked.claim_gate,
            submission_coordinator=dry_submission,
            execution_settings=execution_settings,
            now_provider=now_provider,
        )
        return LiveDryRunOperatorBundle(
            service=LiveDryRunOperationalService(
                coordinator=e2e,
                report_path=resolved_paths.report_path,
            ),
            order_adapter=locked.order_adapter,
            paths=resolved_paths,
        )
