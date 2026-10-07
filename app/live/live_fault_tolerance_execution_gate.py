"""Fail-closed authorization gate for production fault-tolerance execution.

Phase 6-D Step 6C-Q adds an explicit permission boundary in front of an
already-composed runtime. Authorization is denied by default, denied when the
provider fails, and denied for any value other than literal True.

This gate does not start the runtime, execute recovery, access a broker,
schedule work, or alter any live-order hard lock.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from app.live.live_fault_tolerance_execution_boundary import (
    ProductionFaultToleranceExecutionResult,
)
from app.live.live_fault_tolerance_runtime import ProductionFaultToleranceRuntime


class ProductionFaultToleranceExecutionAuthorizationProvider(Protocol):
    def __call__(self) -> bool: ...


class ProductionFaultToleranceExecutionGateDecision(StrEnum):
    ALLOWED = "allowed"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class ProductionFaultToleranceExecutionGateResult:
    decision: ProductionFaultToleranceExecutionGateDecision
    execution: ProductionFaultToleranceExecutionResult | None
    message: str

    @property
    def allowed(self) -> bool:
        return self.decision is ProductionFaultToleranceExecutionGateDecision.ALLOWED

    @property
    def executed(self) -> bool:
        return self.execution is not None


class ProductionFaultToleranceExecutionGate:
    """Explicit fail-closed boundary around one runtime execution."""

    def __init__(
        self,
        *,
        runtime: ProductionFaultToleranceRuntime,
        authorization_provider: ProductionFaultToleranceExecutionAuthorizationProvider | None = None,
    ) -> None:
        self.runtime = runtime
        self.authorization_provider = authorization_provider

    def run_once(self) -> ProductionFaultToleranceExecutionGateResult:
        allowed, message = self._authorize()
        if not allowed:
            return ProductionFaultToleranceExecutionGateResult(
                decision=ProductionFaultToleranceExecutionGateDecision.BLOCKED,
                execution=None,
                message=message,
            )

        execution = self.runtime.run_once()
        return ProductionFaultToleranceExecutionGateResult(
            decision=ProductionFaultToleranceExecutionGateDecision.ALLOWED,
            execution=execution,
            message="production fault-tolerance execution explicitly authorized",
        )

    def _authorize(self) -> tuple[bool, str]:
        if self.authorization_provider is None:
            return False, "production fault-tolerance execution authorization is not configured"

        try:
            value = self.authorization_provider()
        except Exception as error:
            return False, (
                "production fault-tolerance execution authorization failed closed: "
                f"{type(error).__name__}: {error}"
            )

        if value is not True:
            return False, "production fault-tolerance execution authorization was not explicitly granted"

        return True, "production fault-tolerance execution authorized"
