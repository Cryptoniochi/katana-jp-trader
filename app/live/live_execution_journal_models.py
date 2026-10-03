"""Durable live-execution journal models for Phase 6-B Step 1.

These models describe submission-control state only. They do not represent
broker order lifecycle state and contain no broker transport dependency.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class LiveExecutionState(StrEnum):
    """Persistent state of one live-order submission attempt."""

    PREPARED = "prepared"
    CLAIMED = "claimed"
    SUBMISSION_PENDING = "submission_pending"
    SUBMITTED = "submitted"
    ABORTED = "aborted"
    UNKNOWN = "unknown"

    @property
    def is_terminal(self) -> bool:
        return self in {
            LiveExecutionState.SUBMITTED,
            LiveExecutionState.ABORTED,
            LiveExecutionState.UNKNOWN,
        }

    @property
    def blocks_reclaim(self) -> bool:
        """Whether an existing row must never be claimed as a new attempt."""

        return self is not LiveExecutionState.PREPARED


@dataclass(frozen=True, slots=True)
class LiveExecutionJournalRecord:
    """One durable submission-control record."""

    execution_key: str
    order_fingerprint: str
    order_id: str
    signal_id: str
    state: LiveExecutionState
    created_at: datetime
    updated_at: datetime
    claimed_at: datetime | None = None
    submission_pending_at: datetime | None = None
    submitted_at: datetime | None = None
    aborted_at: datetime | None = None
    unknown_at: datetime | None = None
    broker_order_id: str | None = None
    detail: str | None = None

    def __post_init__(self) -> None:
        for name in (
            "execution_key",
            "order_fingerprint",
            "order_id",
            "signal_id",
        ):
            value = getattr(self, name).strip()
            if not value:
                raise ValueError(f"{name} must not be empty.")
            object.__setattr__(self, name, value)

        for name in ("created_at", "updated_at"):
            value = getattr(self, name)
            if value.tzinfo is None:
                raise ValueError(f"{name} must be timezone-aware.")

        if self.updated_at < self.created_at:
            raise ValueError("updated_at must not be earlier than created_at.")

        for name in (
            "claimed_at",
            "submission_pending_at",
            "submitted_at",
            "aborted_at",
            "unknown_at",
        ):
            value = getattr(self, name)
            if value is not None and value.tzinfo is None:
                raise ValueError(f"{name} must be timezone-aware.")

        broker_order_id = (
            None
            if self.broker_order_id is None
            else self.broker_order_id.strip()
        )
        detail = None if self.detail is None else self.detail.strip()
        object.__setattr__(self, "broker_order_id", broker_order_id or None)
        object.__setattr__(self, "detail", detail or None)

        if self.state is LiveExecutionState.PREPARED:
            if any(
                value is not None
                for value in (
                    self.claimed_at,
                    self.submission_pending_at,
                    self.submitted_at,
                    self.aborted_at,
                    self.unknown_at,
                    self.broker_order_id,
                )
            ):
                raise ValueError("PREPARED record contains later-state fields.")

        if self.state is LiveExecutionState.CLAIMED and self.claimed_at is None:
            raise ValueError("CLAIMED record requires claimed_at.")

        if self.state is LiveExecutionState.SUBMISSION_PENDING:
            if self.claimed_at is None or self.submission_pending_at is None:
                raise ValueError(
                    "SUBMISSION_PENDING requires claimed_at and "
                    "submission_pending_at."
                )

        if self.state is LiveExecutionState.SUBMITTED:
            if self.submitted_at is None:
                raise ValueError("SUBMITTED record requires submitted_at.")
            if not self.broker_order_id:
                raise ValueError("SUBMITTED record requires broker_order_id.")

        if self.state is LiveExecutionState.ABORTED and self.aborted_at is None:
            raise ValueError("ABORTED record requires aborted_at.")

        if self.state is LiveExecutionState.UNKNOWN and self.unknown_at is None:
            raise ValueError("UNKNOWN record requires unknown_at.")
