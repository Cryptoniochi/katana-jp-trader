"""Phase 6-A emergency-stop state for the locked live-order boundary.

This module contains no broker transport and performs no network I/O.
It only normalizes already-computed safety state for final boundary checks.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.supervisor.fault_tolerance_models import FaultToleranceDecision


class ThreeWayReconciliationLike(Protocol):
    generated_at: datetime
    state: str
    consistent: bool
    live_order_ready: bool


class FaultToleranceAttemptLike(Protocol):
    checked_at: datetime
    decision: FaultToleranceDecision


@dataclass(frozen=True, slots=True)
class LiveOrderSafetySnapshot:
    """Emergency-stop inputs consumed immediately at the live boundary."""

    safe_stop_active: bool
    reconciliation_consistent: bool
    reconciliation_state: str
    evaluated_at: datetime

    def __post_init__(self) -> None:
        state = self.reconciliation_state.strip()
        if not state:
            raise ValueError("reconciliation_state must not be empty.")
        if self.evaluated_at.tzinfo is None:
            raise ValueError("evaluated_at must be timezone-aware.")
        object.__setattr__(self, "reconciliation_state", state)

    @property
    def is_blocked(self) -> bool:
        return self.safe_stop_active or not self.reconciliation_consistent


def safety_snapshot_from_states(
    *,
    reconciliation_report: ThreeWayReconciliationLike,
    fault_tolerance_attempt: FaultToleranceAttemptLike | None = None,
) -> LiveOrderSafetySnapshot:
    """Build boundary safety state from existing reconciliation/fault results."""

    safe_stop_active = (
        fault_tolerance_attempt is not None
        and fault_tolerance_attempt.decision is FaultToleranceDecision.SAFE_STOP
    )

    # `consistent` is the Phase 5B reconciliation truth value. `live_order_ready`
    # remains False in Phase 6-A by design and is therefore not used to reject
    # an otherwise-consistent report here; the static live-order lock remains
    # the authoritative transmission lock.
    reconciliation_consistent = (
        bool(reconciliation_report.consistent)
        and reconciliation_report.state.strip().lower() == "consistent"
    )

    evaluated_at = reconciliation_report.generated_at
    if (
        fault_tolerance_attempt is not None
        and fault_tolerance_attempt.checked_at > evaluated_at
    ):
        evaluated_at = fault_tolerance_attempt.checked_at

    return LiveOrderSafetySnapshot(
        safe_stop_active=safe_stop_active,
        reconciliation_consistent=reconciliation_consistent,
        reconciliation_state=reconciliation_report.state,
        evaluated_at=evaluated_at,
    )
