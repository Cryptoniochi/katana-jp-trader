"""Durable manual Kill Switch state for Phase 6-D.

This module contains no broker transport, order submission, or network access.
A missing or unreadable state is interpreted by the reader as BLOCKED so the
manual safety input fails closed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


MANUAL_KILL_SWITCH_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class ManualKillSwitchState:
    """Persisted operator-controlled manual Kill Switch state."""

    manual_blocked: bool
    updated_at: datetime
    reason: str

    def __post_init__(self) -> None:
        if self.updated_at.tzinfo is None:
            raise ValueError("updated_at must be timezone-aware.")
        object.__setattr__(
            self,
            "updated_at",
            self.updated_at.astimezone(timezone.utc),
        )
        normalized_reason = self.reason.strip()
        if not normalized_reason:
            raise ValueError("reason must not be empty.")
        object.__setattr__(self, "reason", normalized_reason)
