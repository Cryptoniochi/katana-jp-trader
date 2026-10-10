"""Phase 6-F: reviewed construction boundary for the locked live runtime.

This boundary is the first Phase 6-F component permitted to construct the
freshness-aware locked-live runtime bundle.  Construction is allowed only after
the Step 3 integration gate reports reviewed-unlock readiness.

Construction does not arm the order adapter or transport, does not attach a
broker/network dependency, and does not process or transmit an order.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from app.live.live_runtime_integration_activation_gate import (
    LiveRuntimeIntegrationGateDecision,
    LiveRuntimeIntegrationGateReport,
)
from app.live.locked_live_runtime_composition import LockedLiveRuntimeBundle
from app.live.locked_live_runtime_fresh_composition import FreshLockedLiveRuntimeFactory
from app.live.risk_manager import LiveRiskManager


@dataclass(frozen=True, slots=True)
class LiveRuntimeConstructionResult:
    constructed: bool
    bundle: LockedLiveRuntimeBundle | None
    message: str

    def __post_init__(self) -> None:
        if not self.message.strip():
            raise ValueError("message must not be empty.")
        if self.constructed != (self.bundle is not None):
            raise ValueError("constructed must match bundle presence.")


class LiveRuntimeConstructionBoundary:
    """Construct a fresh locked runtime only after the reviewed Step 3 gate."""

    @staticmethod
    def construct(
        *,
        gate_report: LiveRuntimeIntegrationGateReport,
        database_path: str | Path,
        risk_manager: LiveRiskManager,
        portfolio_provider: Callable,
        reconciliation_report_provider: Callable,
        fault_tolerance_attempt_provider: Callable,
        kill_switch_snapshot_provider: Callable,
        execution_settings=None,
        now_provider=None,
    ) -> LiveRuntimeConstructionResult:
        if (
            gate_report.decision
            is not LiveRuntimeIntegrationGateDecision.READY_FOR_REVIEWED_UNLOCK
            or not gate_report.activation_prerequisites_ready
            or not gate_report.legacy_hard_lock_closed
        ):
            return LiveRuntimeConstructionResult(
                constructed=False,
                bundle=None,
                message=(
                    "Locked live runtime construction is blocked because the "
                    "reviewed activation gate is not ready."
                ),
            )

        bundle = FreshLockedLiveRuntimeFactory.create(
            database_path=database_path,
            risk_manager=risk_manager,
            portfolio_provider=portfolio_provider,
            reconciliation_report_provider=reconciliation_report_provider,
            fault_tolerance_attempt_provider=fault_tolerance_attempt_provider,
            kill_switch_snapshot_provider=kill_switch_snapshot_provider,
            execution_settings=execution_settings,
            now_provider=now_provider,
        )

        if bundle.order_adapter.runtime_armed or bundle.transport.runtime_armed:
            raise RuntimeError(
                "Fresh locked live runtime unexpectedly returned an armed component."
            )

        return LiveRuntimeConstructionResult(
            constructed=True,
            bundle=bundle,
            message=(
                "Fresh locked live runtime was constructed. Order adapter and "
                "broker transport remain runtime-disarmed; no order was processed."
            ),
        )
