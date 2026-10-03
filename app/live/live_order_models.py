"""Phase 6-A locked live-order boundary models.

This module deliberately contains no broker transport dependency.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.live.live_order_safety import LiveOrderSafetySnapshot
from app.live.risk_models import RiskAssessment
from app.risk.kill_switch_models import KillSwitchEvaluation
from app.trading.order_models import TradeOrder


class LiveOrderDecision(StrEnum):
    """Result of evaluating an order at the locked live boundary."""

    LOCKED = "locked"
    BLOCKED = "blocked"
    DUPLICATE = "duplicate"


class LiveOrderBlockReason(StrEnum):
    """Reason why an order cannot cross the live boundary."""

    STATIC_LOCK = "static_lock"
    RUNTIME_LOCK = "runtime_lock"
    NO_TRANSPORT = "no_transport"
    SAFE_STOP = "safe_stop"
    RECONCILIATION = "reconciliation"
    KILL_SWITCH = "kill_switch"
    RISK_REVALIDATION = "risk_revalidation"
    DUPLICATE = "duplicate"
    IDEMPOTENCY_CONFLICT = "idempotency_conflict"


@dataclass(frozen=True, slots=True)
class LiveOrderIntent:
    """Immutable order intent presented to the live-order boundary."""

    order: TradeOrder
    idempotency_key: str
    created_at: datetime

    def __post_init__(self) -> None:
        normalized_key = self.idempotency_key.strip()
        if not normalized_key:
            raise ValueError("idempotency_key must not be empty.")
        if self.created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware.")
        object.__setattr__(self, "idempotency_key", normalized_key)


@dataclass(frozen=True, slots=True)
class LiveOrderBoundaryResult:
    """Auditable result returned by the Phase 6-A live-order boundary."""

    intent: LiveOrderIntent
    decision: LiveOrderDecision
    reason: LiveOrderBlockReason
    evaluated_at: datetime
    risk_assessment: RiskAssessment | None
    kill_switch_evaluation: KillSwitchEvaluation | None
    safety_snapshot: LiveOrderSafetySnapshot | None = None
    message: str = "Live order boundary evaluated."

    def __post_init__(self) -> None:
        if self.evaluated_at.tzinfo is None:
            raise ValueError("evaluated_at must be timezone-aware.")
        if not self.message.strip():
            raise ValueError("message must not be empty.")

    @property
    def is_locked(self) -> bool:
        return self.decision is LiveOrderDecision.LOCKED

    @property
    def is_blocked(self) -> bool:
        return self.decision is LiveOrderDecision.BLOCKED

    @property
    def is_duplicate(self) -> bool:
        return self.decision is LiveOrderDecision.DUPLICATE
