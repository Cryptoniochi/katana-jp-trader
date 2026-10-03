"""Phase 6-C Step 4B-2 freshness-aware locked live runtime composition.

This module layers real runtime safety-state providers on top of the isolated
Step 4A locked-live composition.  The same freshness-aware safety provider is
shared by the live order adapter and the claim gate, so safety is re-read at
both critical boundaries.

No Paper runtime, broker adapter, HTTP client, or order-send path is added.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path

from app.live.execution_mode import ExecutionModeSettings
from app.live.live_order_safety import FaultToleranceAttemptLike, ThreeWayReconciliationLike
from app.live.live_runtime_safety_state import LiveRuntimeSafetyStateProvider
from app.live.locked_live_runtime_composition import (
    KillSwitchSnapshotProvider,
    LockedLiveRuntimeBundle,
    LockedLiveRuntimeFactory,
    MarketPriceProvider,
    PortfolioProvider,
)
from app.live.risk_manager import LiveRiskManager


NowProvider = Callable[[], datetime]
ThreeWayProvider = Callable[[], ThreeWayReconciliationLike | None]
FaultToleranceProvider = Callable[[], FaultToleranceAttemptLike | None]


class FreshLockedLiveRuntimeFactory:
    """Build Step 4A using one shared fail-closed freshness provider."""

    @staticmethod
    def create(
        *,
        database_path: Path,
        risk_manager: LiveRiskManager,
        portfolio_provider: PortfolioProvider,
        reconciliation_report_provider: ThreeWayProvider,
        fault_tolerance_attempt_provider: FaultToleranceProvider,
        kill_switch_snapshot_provider: KillSwitchSnapshotProvider,
        execution_settings: ExecutionModeSettings | None = None,
        market_price_provider: MarketPriceProvider | None = None,
        maximum_reconciliation_age: timedelta = timedelta(minutes=2),
        maximum_future_skew: timedelta = timedelta(seconds=5),
        now_provider: NowProvider | None = None,
    ) -> LockedLiveRuntimeBundle:
        safety_provider = LiveRuntimeSafetyStateProvider(
            reconciliation_report_provider=reconciliation_report_provider,
            fault_tolerance_attempt_provider=fault_tolerance_attempt_provider,
            maximum_reconciliation_age=maximum_reconciliation_age,
            maximum_future_skew=maximum_future_skew,
            now_provider=now_provider,
        )

        return LockedLiveRuntimeFactory.create(
            database_path=database_path,
            risk_manager=risk_manager,
            portfolio_provider=portfolio_provider,
            safety_snapshot_provider=safety_provider,
            kill_switch_snapshot_provider=kill_switch_snapshot_provider,
            execution_settings=execution_settings,
            market_price_provider=market_price_provider,
            now_provider=now_provider,
        )
