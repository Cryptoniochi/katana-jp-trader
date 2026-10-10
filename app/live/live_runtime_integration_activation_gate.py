"""Phase 6-F Step 3: fail-closed runtime integration activation gate.

This module connects the Step 2 activation-readiness report to the existing
Phase 6-C runtime integration seam without activating it.  The legacy hard lock
must remain closed.  No live runtime bundle is constructed and no order is
processed.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.live.live_runtime_activation_boundary import LiveRuntimeActivationReport
from app.live.locked_live_runtime_integration import (
    LOCKED_LIVE_RUNTIME_INTEGRATION_ENABLED,
)


class LiveRuntimeIntegrationGateDecision(StrEnum):
    BLOCKED = "blocked"
    READY_FOR_REVIEWED_UNLOCK = "ready_for_reviewed_unlock"


@dataclass(frozen=True, slots=True)
class LiveRuntimeIntegrationGateReport:
    generated_at: datetime
    decision: LiveRuntimeIntegrationGateDecision
    activation_prerequisites_ready: bool
    legacy_hard_lock_closed: bool
    message: str

    def __post_init__(self) -> None:
        if self.generated_at.tzinfo is None:
            raise ValueError("generated_at must be timezone-aware.")
        if not self.message.strip():
            raise ValueError("message must not be empty.")
        if self.decision is LiveRuntimeIntegrationGateDecision.READY_FOR_REVIEWED_UNLOCK:
            if not self.activation_prerequisites_ready:
                raise ValueError(
                    "READY_FOR_REVIEWED_UNLOCK requires activation prerequisites."
                )
            if not self.legacy_hard_lock_closed:
                raise ValueError(
                    "READY_FOR_REVIEWED_UNLOCK requires the legacy hard lock closed."
                )


class LiveRuntimeIntegrationActivationGate:
    """Read-only final gate before a separately reviewed runtime unlock."""

    @staticmethod
    def evaluate(
        activation_report: LiveRuntimeActivationReport,
    ) -> LiveRuntimeIntegrationGateReport:
        prerequisites_ready = activation_report.runtime_activation_ready is True
        hard_lock_closed = LOCKED_LIVE_RUNTIME_INTEGRATION_ENABLED is False

        if prerequisites_ready and hard_lock_closed:
            return LiveRuntimeIntegrationGateReport(
                generated_at=activation_report.generated_at,
                decision=LiveRuntimeIntegrationGateDecision.READY_FOR_REVIEWED_UNLOCK,
                activation_prerequisites_ready=True,
                legacy_hard_lock_closed=True,
                message=(
                    "Runtime integration prerequisites are ready for a separately "
                    "reviewed unlock. The legacy runtime hard lock remains closed; "
                    "no live runtime bundle was constructed and no order was processed."
                ),
            )

        return LiveRuntimeIntegrationGateReport(
            generated_at=activation_report.generated_at,
            decision=LiveRuntimeIntegrationGateDecision.BLOCKED,
            activation_prerequisites_ready=prerequisites_ready,
            legacy_hard_lock_closed=hard_lock_closed,
            message=(
                "Runtime integration remains blocked. No live runtime bundle was "
                "constructed and no order was processed."
            ),
        )
