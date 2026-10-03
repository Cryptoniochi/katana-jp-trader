"""Phase 6-C models for the locked live broker transport boundary.

This module contains no broker adapter and performs no network I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.trading.order_models import TradeOrder


class LiveTransportDecision(StrEnum):
    """Outcome of evaluating the locked transport boundary."""

    LOCKED = "locked"


class LiveTransportLockReason(StrEnum):
    """Reason why live transport remains unavailable."""

    STATIC_LOCK = "static_lock"
    RUNTIME_LOCK = "runtime_lock"
    EXECUTION_MODE_LOCK = "execution_mode_lock"
    NO_TRANSPORT = "no_transport"


@dataclass(frozen=True, slots=True)
class LiveTransportRequest:
    """Immutable request presented to the live transport boundary."""

    execution_key: str
    order: TradeOrder
    requested_at: datetime

    def __post_init__(self) -> None:
        execution_key = self.execution_key.strip()
        if not execution_key:
            raise ValueError("execution_key must not be empty.")
        if self.requested_at.tzinfo is None:
            raise ValueError("requested_at must be timezone-aware.")
        object.__setattr__(self, "execution_key", execution_key)


@dataclass(frozen=True, slots=True)
class LiveTransportResult:
    """Auditable result from the locked transport boundary."""

    request: LiveTransportRequest
    decision: LiveTransportDecision
    reason: LiveTransportLockReason
    evaluated_at: datetime
    message: str

    def __post_init__(self) -> None:
        if self.evaluated_at.tzinfo is None:
            raise ValueError("evaluated_at must be timezone-aware.")
        message = self.message.strip()
        if not message:
            raise ValueError("message must not be empty.")
        object.__setattr__(self, "message", message)
