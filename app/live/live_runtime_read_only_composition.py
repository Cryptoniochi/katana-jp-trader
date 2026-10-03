"""Compose Phase 6-C read-only runtime state providers.

This module only wires already-existing read-only sources.  Construction does
not evaluate the providers, mutate RuntimeSession state, access the network,
issue a kabu Station token, or create any live execution component.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from app.live.kabu_station_read_only_report_reader import (
    KabuStationReadOnlyReportReader,
)
from app.live.live_daily_loss_state import (
    DailyClosedTradeRepository,
    LiveDailyLossStateProvider,
)
from app.live.live_runtime_operational_state import (
    KabuStationBrokerAvailabilityProvider,
    RuntimeHealthOkProvider,
    RuntimeSessionActivityProvider,
    RuntimeSessionHeartbeatAliveProvider,
)
from app.runtime.runtime_health_monitor_service import (
    RuntimeHealthMonitorService,
)
from app.runtime.session_service import RuntimeSessionService


NowProvider = Callable[[], datetime]


@dataclass(frozen=True, slots=True)
class LiveRuntimeReadOnlyProviders:
    """Providers consumed by the disabled Phase 6-C live attachment."""

    daily_profit_loss_provider: Callable[[], float]
    consecutive_loss_count_provider: Callable[[], int]
    runtime_health_ok_provider: Callable[[], bool]
    heartbeat_alive_provider: Callable[[], bool]
    broker_available_provider: Callable[[], bool]


class LiveRuntimeReadOnlyProviderFactory:
    """Build live-safety inputs without evaluating or mutating them."""

    @staticmethod
    def create(
        *,
        daily_trade_repository: DailyClosedTradeRepository,
        runtime_session_service: RuntimeSessionService,
        kabu_station_report_path: Path,
        runtime_health_monitor: RuntimeHealthMonitorService | None = None,
        heartbeat_stale_after_seconds: float = 180.0,
        broker_maximum_age_seconds: float = 120.0,
        broker_maximum_future_skew_seconds: float = 5.0,
        now_provider: NowProvider | None = None,
    ) -> LiveRuntimeReadOnlyProviders:
        daily_loss_state = LiveDailyLossStateProvider(
            repository=daily_trade_repository,
            now_provider=now_provider,
        )

        runtime_activity = RuntimeSessionActivityProvider(
            session_service=runtime_session_service,
            now_provider=now_provider,
        )
        runtime_health = RuntimeHealthOkProvider(
            activity_provider=runtime_activity,
            monitor=runtime_health_monitor,
        )
        heartbeat_alive = RuntimeSessionHeartbeatAliveProvider(
            session_service=runtime_session_service,
            stale_after_seconds=heartbeat_stale_after_seconds,
            now_provider=now_provider,
        )

        saved_broker_snapshot = KabuStationReadOnlyReportReader(
            Path(kabu_station_report_path)
        )
        broker_available = KabuStationBrokerAvailabilityProvider(
            snapshot_provider=saved_broker_snapshot,
            maximum_age_seconds=broker_maximum_age_seconds,
            maximum_future_skew_seconds=broker_maximum_future_skew_seconds,
            now_provider=now_provider,
        )

        return LiveRuntimeReadOnlyProviders(
            daily_profit_loss_provider=(
                daily_loss_state.daily_realized_profit_loss
            ),
            consecutive_loss_count_provider=(
                daily_loss_state.consecutive_loss_count
            ),
            runtime_health_ok_provider=runtime_health,
            heartbeat_alive_provider=heartbeat_alive,
            broker_available_provider=broker_available,
        )
