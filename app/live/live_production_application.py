"""Production wiring for the Live market-session application.

This module joins the Phase 6C Live-only components without importing or
constructing PaperBroker.  Concrete broker/runtime dependencies remain owned by
the caller/composition layer; this module is the application seam used by the
market-session entrypoint.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Callable, Protocol, Sequence

from app.live.execution_mode import ExecutionModeSettings, TradingExecutionMode
from app.live.final_live_runtime_composition import FinalLiveRuntimeBundle
from app.live.live_production_runner import (
    LiveEntryIntent,
    LiveProductionCycleResult,
    LiveProductionRunner,
)
from app.live.live_signal_execution_bridge import FinalLiveEntrySubmitter


class LiveProductionWiringError(RuntimeError):
    """Raised when the production Live application is not safely composed."""


class ProtectiveCycle(Protocol):
    def __call__(self, trading_date: date) -> object: ...


@dataclass(frozen=True, slots=True)
class LiveProductionApplication:
    """One-cycle production Live application assembled from final Live runtime."""

    runner: LiveProductionRunner

    def run_cycle(self, *, trading_date: date) -> LiveProductionCycleResult:
        return self.runner.run_cycle(trading_date=trading_date)


class LiveProductionApplicationFactory:
    """Wire signal discovery to FinalLiveRuntime without any Paper fallback."""

    @staticmethod
    def create(
        *,
        execution_settings: ExecutionModeSettings,
        final_runtime: FinalLiveRuntimeBundle,
        entry_intent_provider: Callable[[], Sequence[LiveEntryIntent]],
        protective_cycle: ProtectiveCycle | None = None,
    ) -> LiveProductionApplication:
        if execution_settings.mode is not TradingExecutionMode.LIVE:
            raise LiveProductionWiringError(
                "Live production application requires execution mode LIVE."
            )
        if final_runtime is None:
            raise LiveProductionWiringError(
                "FinalLiveRuntimeBundle is required; Paper fallback is forbidden."
            )
        if entry_intent_provider is None:
            raise LiveProductionWiringError(
                "A broker-independent Live entry intent provider is required."
            )
        if protective_cycle is None:
            protective_cycle = final_runtime.protective_stop_cycle

        # Production composition supplies both durable reconciliation objects.
        # Minimal/test runtimes from the existing application seam may supply
        # neither; preserve that compatibility without permitting half-wiring.
        reconciliation_registry = getattr(
            final_runtime, "entry_reconciliation_registry", None
        )
        reconciliation_cycle = getattr(
            final_runtime, "entry_reconciliation_cycle", None
        )
        if (reconciliation_registry is None) != (reconciliation_cycle is None):
            raise LiveProductionWiringError(
                "Live entry reconciliation registry and cycle must be wired together."
            )

        submitter = FinalLiveEntrySubmitter(
            prepared_tracking_flow=final_runtime.prepared_tracking_flow,
            reconciliation_registry=reconciliation_registry,
        )
        runner = LiveProductionRunner(
            execution_settings=execution_settings,
            entry_intent_provider=entry_intent_provider,
            entry_submitter=submitter,
            protective_cycle=protective_cycle,
            reconciliation_cycle=reconciliation_cycle,
            position_protection_reconciliation=getattr(
                final_runtime, "position_protection_reconciliation", None
            ),
        )
        return LiveProductionApplication(runner=runner)
