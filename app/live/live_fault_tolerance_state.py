"""Read-only bridge from the existing fault-tolerance service to live safety state.

Phase 6-D keeps live-order transmission disabled.  This module only exposes the
latest already-computed FaultToleranceAttempt without running recovery,
mutating supervisor state, or performing network I/O.
"""

from __future__ import annotations

from typing import Protocol

from app.supervisor.fault_tolerance_models import FaultToleranceAttempt


class FaultToleranceHistoryProvider(Protocol):
    """Minimal read-only contract implemented by FaultToleranceService."""

    def history(self) -> tuple[FaultToleranceAttempt, ...]: ...


class LatestFaultToleranceAttemptProvider:
    """Return the latest existing fault-tolerance attempt, if one exists."""

    def __init__(self, service: FaultToleranceHistoryProvider) -> None:
        self.service = service

    def __call__(self) -> FaultToleranceAttempt | None:
        history = self.service.history()
        if not history:
            return None
        return history[-1]
