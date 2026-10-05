from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable

from app.live.execution_mode import ExecutionModeSettings, TradingExecutionMode
from app.live.final_live_readiness import FinalLiveReadinessGate
from app.live.live_dry_run_e2e_coordinator import LiveDryRunE2ECoordinator
from app.live.live_dry_run_operational_service import LiveDryRunOperationalService
from app.live.live_dry_run_production_read_only import (
    ProductionDryRunReadOnlyFactory,
    ProductionReadOnlyPaths,
)
from app.live.live_transport_dry_run import SimulatedLiveBrokerTransport
from app.live.live_transport_dry_run_coordinator import DryRunLiveSubmissionCoordinator
from app.live.locked_live_runtime_composition import LockedLiveRuntimeFactory
from app.live.risk_manager import LiveRiskManager
from app.trading.order_models import TradeOrder

NowProvider = Callable[[], datetime]
MarketPriceProvider = Callable[[str], float]


@dataclass(frozen=True, slots=True)
class LiveDryRunOperatorPaths:
    database_path: Path = Path("data/live_dry_run.db")
    report_path: Path = Path("reports/live/live_dry_run_audit.json")

    def __post_init__(self) -> None:
        database = Path(self.database_path)
        if database == Path("data/katana.db"):
            raise ValueError("Dry-run execution database must not be data/katana.db.")
        object.__setattr__(self, "database_path", database)
        object.__setattr__(self, "report_path", Path(self.report_path))


@dataclass(frozen=True, slots=True)
class LiveDryRunOperatorBundle:
    service: LiveDryRunOperationalService
    order_adapter: object
    paths: LiveDryRunOperatorPaths

    def create_intent(self, order: TradeOrder):
        return self.order_adapter.create_intent(order)


class LiveDryRunOperatorComposition:
    """Compose the isolated dry-run execution path from explicit providers."""

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
        market_price_provider: MarketPriceProvider | None = None,
        max_daily_loss: float = 50_000.0,
        max_consecutive_losses: int = 3,
        now_provider: NowProvider | None = None,
    ) -> LiveDryRunOperatorBundle:
        resolved_paths = paths or LiveDryRunOperatorPaths()
        settings = ExecutionModeSettings(
            mode=TradingExecutionMode.LIVE,
            live_armed=True,
            live_confirmation=live_confirmation,
        )
        readiness = FinalLiveReadinessGate(
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
            execution_settings=settings,
            market_price_provider=market_price_provider,
            now_provider=now_provider,
        )
        simulated = SimulatedLiveBrokerTransport(
            execution_settings=settings,
            now_provider=now_provider,
        )
        submission = DryRunLiveSubmissionCoordinator(
            journal=locked.journal,
            submission_boundary=locked.submission_boundary,
            transport=simulated,
            now_provider=now_provider,
        )
        e2e = LiveDryRunE2ECoordinator(
            readiness_gate=readiness,
            preparation_service=locked.preparation_service,
            claim_gate=locked.claim_gate,
            submission_coordinator=submission,
            execution_settings=settings,
            now_provider=now_provider,
        )
        service = LiveDryRunOperationalService(
            coordinator=e2e,
            report_path=resolved_paths.report_path,
        )
        # Explicitly exercise the daily token contract during construction only
        # through the normal E2E path later; construction itself performs no state IO.
        _ = trading_date
        return LiveDryRunOperatorBundle(
            service=service,
            order_adapter=locked.order_adapter,
            paths=resolved_paths,
        )

    @staticmethod
    def create_from_production_read_only(
        *,
        trading_date: date,
        live_confirmation: str,
        paths: LiveDryRunOperatorPaths | None = None,
        read_only_paths: ProductionReadOnlyPaths | None = None,
        risk_manager: LiveRiskManager | None = None,
        market_price_provider: MarketPriceProvider | None = None,
        max_daily_loss: float = 50_000.0,
        max_consecutive_losses: int = 3,
        runtime_stale_after_seconds: float = 180.0,
        broker_maximum_age_seconds: float = 120.0,
        now_provider: NowProvider | None = None,
    ) -> LiveDryRunOperatorBundle:
        read_only = ProductionDryRunReadOnlyFactory.create(
            paths=read_only_paths,
            max_daily_loss=max_daily_loss,
            max_consecutive_losses=max_consecutive_losses,
            runtime_stale_after_seconds=runtime_stale_after_seconds,
            broker_maximum_age_seconds=broker_maximum_age_seconds,
            now_provider=now_provider,
        )
        p = read_only.providers
        return LiveDryRunOperatorComposition.create(
            trading_date=trading_date,
            live_confirmation=live_confirmation,
            portfolio_provider=p.portfolio_provider,
            safety_snapshot_provider=read_only.safety_snapshot_provider,
            kill_switch_snapshot_provider=read_only.kill_switch_snapshot_provider,
            manual_blocked_provider=p.manual_blocked_provider,
            daily_profit_loss_provider=p.daily_profit_loss_provider,
            consecutive_loss_count_provider=p.consecutive_loss_count_provider,
            runtime_health_ok_provider=p.runtime_health_ok_provider,
            heartbeat_alive_provider=p.heartbeat_alive_provider,
            broker_available_provider=p.broker_available_provider,
            paths=paths,
            risk_manager=risk_manager,
            market_price_provider=market_price_provider,
            max_daily_loss=max_daily_loss,
            max_consecutive_losses=max_consecutive_losses,
            now_provider=now_provider,
        )
