"""Compose read-only live runtime state providers.

Phase 6-D keeps every live-order transmission lock closed. This module only
wires already-existing saved/read-only state. Construction does not evaluate
providers, mutate runtime state, access the network, issue a kabu Station
token, or create any live execution component.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from app.live.kabu_station_read_only import KabuStationReadOnlySnapshot
from app.live.kabu_station_read_only_report_reader import KabuStationReadOnlyReportReader
from app.live.live_daily_loss_state import DailyClosedTradeRepository, LiveDailyLossStateProvider
from app.live.live_equity_peak_state import LiveEquityPeakStore
from app.live.live_fault_tolerance_saved_state_reader import (
    FaultToleranceSavedStateReader,
    SavedFaultToleranceAttemptView,
)
from app.live.live_risk_portfolio_state import KabuStationRiskPortfolioProvider
from app.live.live_runtime_operational_state import (
    KabuStationBrokerAvailabilityProvider,
    RuntimeHealthOkProvider,
    RuntimeSessionActivityProvider,
    RuntimeSessionHeartbeatAliveProvider,
)
from app.live.live_runtime_state_providers import ThreeWayReconciliationReportReader
from app.live.risk_models import RiskPortfolioSnapshot
from app.live.three_way_reconciliation import ThreeWayReconciliationReport
from app.runtime.runtime_health_monitor_service import RuntimeHealthMonitorService
from app.runtime.session_service import RuntimeSessionService

NowProvider = Callable[[], datetime]


@dataclass(frozen=True, slots=True)
class LiveRuntimeReadOnlyProviders:
    """Read-only providers for the disabled live runtime attachment."""

    daily_profit_loss_provider: Callable[[], float]
    consecutive_loss_count_provider: Callable[[], int]
    runtime_health_ok_provider: Callable[[], bool]
    heartbeat_alive_provider: Callable[[], bool]
    broker_available_provider: Callable[[], bool]
    saved_broker_snapshot_provider: Callable[[], KabuStationReadOnlySnapshot | None]
    portfolio_provider: Callable[[], RiskPortfolioSnapshot]
    reconciliation_report_provider: Callable[[], ThreeWayReconciliationReport | None]
    fault_tolerance_attempt_provider: Callable[
        [], SavedFaultToleranceAttemptView | None
    ]


class LiveRuntimeReadOnlyProviderFactory:
    """Build live-safety inputs without evaluating or mutating them."""

    @staticmethod
    def create(
        *,
        daily_trade_repository: DailyClosedTradeRepository,
        runtime_session_service: RuntimeSessionService,
        kabu_station_report_path: Path,
        live_equity_peak_path: Path | None = None,
        three_way_reconciliation_report_path: Path | None = None,
        fault_tolerance_state_path: Path | None = None,
        runtime_health_monitor: RuntimeHealthMonitorService | None = None,
        heartbeat_stale_after_seconds: float = 180.0,
        broker_maximum_age_seconds: float = 120.0,
        broker_maximum_future_skew_seconds: float = 5.0,
        now_provider: NowProvider | None = None,
    ) -> LiveRuntimeReadOnlyProviders:
        effective_now_provider = (
            now_provider
            if now_provider is not None
            else lambda: datetime.now(timezone.utc)
        )

        daily_loss_state = LiveDailyLossStateProvider(
            repository=daily_trade_repository,
            now_provider=effective_now_provider,
        )
        runtime_activity = RuntimeSessionActivityProvider(
            session_service=runtime_session_service,
            now_provider=effective_now_provider,
        )
        runtime_health = RuntimeHealthOkProvider(
            activity_provider=runtime_activity,
            monitor=runtime_health_monitor,
        )
        heartbeat_alive = RuntimeSessionHeartbeatAliveProvider(
            session_service=runtime_session_service,
            stale_after_seconds=heartbeat_stale_after_seconds,
            now_provider=effective_now_provider,
        )

        saved_broker_snapshot = KabuStationReadOnlyReportReader(
            Path(kabu_station_report_path)
        )
        broker_available = KabuStationBrokerAvailabilityProvider(
            snapshot_provider=saved_broker_snapshot,
            maximum_age_seconds=broker_maximum_age_seconds,
            maximum_future_skew_seconds=broker_maximum_future_skew_seconds,
            now_provider=effective_now_provider,
        )

        peak_path = (
            Path(live_equity_peak_path)
            if live_equity_peak_path is not None
            else Path(kabu_station_report_path).with_name("live_equity_peak.json")
        )
        peak_store = LiveEquityPeakStore(
            peak_path,
            now_provider=effective_now_provider,
        )
        portfolio = KabuStationRiskPortfolioProvider(
            snapshot_provider=saved_broker_snapshot,
            daily_profit_loss_provider=daily_loss_state.daily_realized_profit_loss,
            consecutive_loss_count_provider=daily_loss_state.consecutive_loss_count,
            peak_equity_provider=lambda: peak_store.read().peak_equity,
            now_provider=effective_now_provider,
        )

        if three_way_reconciliation_report_path is None:
            def reconciliation_report_provider() -> None:
                return None
        else:
            reconciliation_reader = ThreeWayReconciliationReportReader(
                Path(three_way_reconciliation_report_path)
            )
            reconciliation_report_provider = reconciliation_reader.read

        if fault_tolerance_state_path is None:
            def fault_tolerance_attempt_provider() -> None:
                return None
        else:
            fault_tolerance_reader = FaultToleranceSavedStateReader(
                Path(fault_tolerance_state_path)
            )
            fault_tolerance_attempt_provider = fault_tolerance_reader

        return LiveRuntimeReadOnlyProviders(
            daily_profit_loss_provider=daily_loss_state.daily_realized_profit_loss,
            consecutive_loss_count_provider=daily_loss_state.consecutive_loss_count,
            runtime_health_ok_provider=runtime_health,
            heartbeat_alive_provider=heartbeat_alive,
            broker_available_provider=broker_available,
            saved_broker_snapshot_provider=saved_broker_snapshot,
            portfolio_provider=portfolio,
            reconciliation_report_provider=reconciliation_report_provider,
            fault_tolerance_attempt_provider=fault_tolerance_attempt_provider,
        )
