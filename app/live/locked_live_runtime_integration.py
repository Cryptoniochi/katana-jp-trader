"""Phase 6-C Step 4C-1 disabled locked-live runtime integration point.

This module intentionally does not integrate with the existing Paper runtime
yet.  It defines the runtime-facing seam first and proves that the seam cannot
activate live execution during Phase 6-C.

Safety invariants:
- the integration compile-time/default lock is False;
- callers cannot enable it through constructor/runtime configuration;
- no locked-live bundle is constructed while disabled;
- no SQLite live tables are created while disabled;
- no order intent is evaluated while disabled;
- no broker client, HTTP client, kabu Station endpoint, or send operation exists.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Callable

from app.live.execution_mode import ExecutionModeSettings
from app.live.live_order_safety import (
    FaultToleranceAttemptLike,
    ThreeWayReconciliationLike,
)
from app.live.locked_live_runtime_composition import (
    KillSwitchSnapshotProvider,
    MarketPriceProvider,
    PortfolioProvider,
)
from app.live.locked_live_runtime_fresh_composition import (
    FreshLockedLiveRuntimeFactory,
)
from app.live.risk_manager import LiveRiskManager
from app.trading.order_models import TradeOrder


# Phase 6-C hard lock.  This must remain False until a separately reviewed
# runtime-unlock phase.
LOCKED_LIVE_RUNTIME_INTEGRATION_ENABLED = False


class LockedLiveRuntimeIntegrationDecision(StrEnum):
    DISABLED = "disabled"


@dataclass(frozen=True, slots=True)
class LockedLiveRuntimeIntegrationResult:
    decision: LockedLiveRuntimeIntegrationDecision
    evaluated_at: datetime
    message: str

    def __post_init__(self) -> None:
        if self.evaluated_at.tzinfo is None:
            raise ValueError("evaluated_at must be timezone-aware.")
        if not self.message.strip():
            raise ValueError("message must not be empty.")

    @property
    def is_disabled(self) -> bool:
        return self.decision is LockedLiveRuntimeIntegrationDecision.DISABLED


NowProvider = Callable[[], datetime]
ThreeWayProvider = Callable[[], ThreeWayReconciliationLike | None]
FaultToleranceProvider = Callable[[], FaultToleranceAttemptLike | None]


class LockedLiveRuntimeIntegration:
    """Runtime seam that is deliberately inert throughout Phase 6-C."""

    def __init__(
        self,
        *,
        database_path: Path,
        risk_manager: LiveRiskManager,
        portfolio_provider: PortfolioProvider,
        reconciliation_report_provider: ThreeWayProvider,
        fault_tolerance_attempt_provider: FaultToleranceProvider,
        kill_switch_snapshot_provider: KillSwitchSnapshotProvider,
        execution_settings: ExecutionModeSettings | None = None,
        market_price_provider: MarketPriceProvider | None = None,
        now_provider: NowProvider | None = None,
    ) -> None:
        self.database_path = Path(database_path)
        self.risk_manager = risk_manager
        self.portfolio_provider = portfolio_provider
        self.reconciliation_report_provider = reconciliation_report_provider
        self.fault_tolerance_attempt_provider = fault_tolerance_attempt_provider
        self.kill_switch_snapshot_provider = kill_switch_snapshot_provider
        self.execution_settings = execution_settings
        self.market_price_provider = market_price_provider
        self.now_provider = (
            now_provider
            if now_provider is not None
            else lambda: datetime.now(timezone.utc)
        )

    @classmethod
    def disabled_attachment(
        cls,
        *,
        database_path: Path,
        now_provider: NowProvider | None = None,
    ) -> "LockedLiveRuntimeIntegration":
        """Create the inert runtime attachment used during Phase 6-C.

        The attachment deliberately has no healthy live-state dependencies.
        Every future state dependency is fail-closed if it is ever evaluated,
        while ``process`` remains hard-disabled by the Phase 6-C lock.
        """

        def unavailable_portfolio_provider():
            raise RuntimeError(
                "Live portfolio state is not connected in Phase 6-C."
            )

        def unavailable_reconciliation_provider():
            return None

        def unavailable_fault_tolerance_provider():
            return None

        def unavailable_kill_switch_provider():
            raise RuntimeError(
                "Live kill-switch state is not connected in Phase 6-C."
            )

        return cls(
            database_path=database_path,
            risk_manager=LiveRiskManager(),
            portfolio_provider=unavailable_portfolio_provider,
            reconciliation_report_provider=(
                unavailable_reconciliation_provider
            ),
            fault_tolerance_attempt_provider=(
                unavailable_fault_tolerance_provider
            ),
            kill_switch_snapshot_provider=(
                unavailable_kill_switch_provider
            ),
            execution_settings=None,
            market_price_provider=None,
            now_provider=now_provider,
        )

    @property
    def enabled(self) -> bool:
        """Return the compile-time integration state.

        There is intentionally no setter and no constructor flag capable of
        overriding the Phase 6-C hard lock.
        """

        return LOCKED_LIVE_RUNTIME_INTEGRATION_ENABLED

    def process(self, order: TradeOrder) -> LockedLiveRuntimeIntegrationResult:
        """Accept the future runtime call shape but remain completely inert."""

        # Keep the parameter part of the explicit future integration contract.
        # It is deliberately not inspected or evaluated while disabled.
        _ = order

        if not LOCKED_LIVE_RUNTIME_INTEGRATION_ENABLED:
            return LockedLiveRuntimeIntegrationResult(
                decision=LockedLiveRuntimeIntegrationDecision.DISABLED,
                evaluated_at=self._current_time(),
                message=(
                    "Locked live runtime integration is disabled in Phase 6-C; "
                    "no live execution component was constructed or invoked."
                ),
            )

        # Defense in depth: even if the module constant were monkeypatched,
        # Step 4C-1 still does not activate the fresh locked-live composition.
        # A future reviewed phase must replace this explicit stop with a
        # separately tested activation path.
        return LockedLiveRuntimeIntegrationResult(
            decision=LockedLiveRuntimeIntegrationDecision.DISABLED,
            evaluated_at=self._current_time(),
            message=(
                "Locked live runtime integration has no activation path in "
                "Phase 6-C."
            ),
        )

    def _current_time(self) -> datetime:
        current = self.now_provider()
        if current.tzinfo is None:
            raise ValueError("now_provider must return a timezone-aware datetime.")
        return current.astimezone(timezone.utc)
