"""Phase 6-F Step 2: read-only runtime integration activation boundary.

Consumes the Phase 6-F transition report and determines whether the runtime
integration stage is ready for a future reviewed activation. No activation is
performed and no live runtime bundle is constructed.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from app.live.live_activation_transition import LiveActivationTransitionReport

class LiveRuntimeActivationDecision(StrEnum):
    BLOCKED = "blocked"
    ACTIVATION_READY = "activation_ready"

@dataclass(frozen=True, slots=True)
class LiveRuntimeActivationReport:
    generated_at: datetime
    decision: LiveRuntimeActivationDecision
    runtime_activation_ready: bool
    message: str

    def __post_init__(self) -> None:
        if self.generated_at.tzinfo is None:
            raise ValueError("generated_at must be timezone-aware.")
        if not self.message.strip():
            raise ValueError("message must not be empty.")
        if self.decision is LiveRuntimeActivationDecision.ACTIVATION_READY and not self.runtime_activation_ready:
            raise ValueError("ACTIVATION_READY requires runtime_activation_ready=True.")
        if self.decision is LiveRuntimeActivationDecision.BLOCKED and self.runtime_activation_ready:
            raise ValueError("BLOCKED requires runtime_activation_ready=False.")

class LiveRuntimeActivationBoundary:
    """Read-only gate for the first execution activation stage."""

    @staticmethod
    def evaluate(transition_report: LiveActivationTransitionReport) -> LiveRuntimeActivationReport:
        ready = transition_report.runtime_activation_ready is True
        if ready:
            return LiveRuntimeActivationReport(
                generated_at=transition_report.generated_at,
                decision=LiveRuntimeActivationDecision.ACTIVATION_READY,
                runtime_activation_ready=True,
                message=(
                    "Runtime integration activation prerequisites are ready. "
                    "No runtime integration, broker transport, or order transmission lock has been changed."
                ),
            )
        return LiveRuntimeActivationReport(
            generated_at=transition_report.generated_at,
            decision=LiveRuntimeActivationDecision.BLOCKED,
            runtime_activation_ready=False,
            message=(
                "Runtime integration activation remains blocked. "
                "No execution component was constructed or invoked."
            ),
        )
