"""Explicit dependency contract for production fault-tolerance recovery.

Phase 6-D Step 6C-L does not choose or construct a live RecoveryManager.
It records the exact recovery-capable dependency that a future reviewed
production composition must inject.

This keeps operator/runtime composition fail-closed: no broker, network client,
repository, reconciliation service, or portfolio service is created here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.live.recovery_models import RecoveryResult


class ProductionFaultToleranceRecovery(Protocol):
    """Minimal recovery capability required by FaultToleranceService."""

    def recover(
        self,
        *,
        continue_on_error: bool = False,
    ) -> RecoveryResult: ...


@dataclass(frozen=True, slots=True)
class ProductionFaultToleranceDependencies:
    """Already-created operational dependencies approved for composition."""

    recovery: ProductionFaultToleranceRecovery
