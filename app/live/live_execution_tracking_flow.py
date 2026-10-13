"""Durable live execution tracking flow for Phase 4B.

The flow captures and persists the authoritative pre-submission real-position
baseline before any activated submission can occur.  After a durable SUBMITTED
journal record exists, broker execution reconciliation is followed by a fresh
real-position consistency check.

This module does not create a broker transport and never retries, cancels, or
replaces an order.  A restart can resume tracking because the baseline is
stored in SQLite before submission.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from app.live.activated_live_submission_coordinator import (
    ActivatedLiveSubmissionDecision,
    ActivatedLiveSubmissionResult,
)
from app.live.live_execution_position_consistency import (
    LiveExecutionPositionConsistencyDecision,
    LiveExecutionPositionConsistencyResult,
    LiveExecutionPositionConsistencyService,
    LivePositionBaseline,
)
from app.live.live_submitted_execution_lifecycle import (
    LiveSubmittedExecutionLifecycle,
    LiveSubmittedExecutionResult,
)
from app.trading.order_models import TradeOrder


class LiveExecutionTrackingDecision(StrEnum):
    SUBMISSION_BLOCKED = "submission_blocked"
    SUBMITTED = "submitted"
    SUBMISSION_UNKNOWN = "submission_unknown"
    WORKING_CONSISTENT = "working_consistent"
    PARTIALLY_FILLED_CONSISTENT = "partially_filled_consistent"
    FILLED_CONSISTENT = "filled_consistent"
    TERMINATED_CONSISTENT = "terminated_consistent"
    POSITION_MISMATCH = "position_mismatch"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class LiveExecutionTrackingResult:
    execution_key: str
    decision: LiveExecutionTrackingDecision
    baseline: LivePositionBaseline
    submission: ActivatedLiveSubmissionResult | None = None
    lifecycle: LiveSubmittedExecutionResult | None = None
    consistency: LiveExecutionPositionConsistencyResult | None = None
    detail: str = ""

    @property
    def may_retry_submission(self) -> bool:
        return False

    @property
    def position_confirmed(self) -> bool:
        return (
            self.consistency is not None
            and self.consistency.decision
            is LiveExecutionPositionConsistencyDecision.CONSISTENT
        )


class LivePositionBaselineConflictError(RuntimeError):
    pass


class SQLiteLivePositionBaselineRepository:
    """Persist one immutable pre-submission position baseline per execution."""

    TABLE_NAME = "live_execution_position_baseline"

    def __init__(self, database_path: Path) -> None:
        self.database_path = Path(database_path)
        self._initialize()

    def save_once(
        self,
        execution_key: str,
        *,
        order: TradeOrder,
        baseline: LivePositionBaseline,
    ) -> LivePositionBaseline:
        key = self._required(execution_key, "execution_key")
        if baseline.code != order.code:
            raise ValueError("baseline code does not match order code")
        try:
            with self._connect() as connection:
                connection.execute(
                    f"""
                    INSERT OR IGNORE INTO {self.TABLE_NAME}
                        (execution_key, order_id, signal_id, code, quantity)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (key, order.order_id, order.signal_id, order.code, baseline.quantity),
                )
                connection.commit()
                row = connection.execute(
                    f"""
                    SELECT order_id, signal_id, code, quantity
                    FROM {self.TABLE_NAME}
                    WHERE execution_key = ?
                    """,
                    (key,),
                ).fetchone()
        except sqlite3.Error as exc:
            raise RuntimeError("Could not persist live position baseline.") from exc
        if row is None:
            raise RuntimeError("Persisted live position baseline disappeared.")
        existing = (str(row[0]), str(row[1]), str(row[2]), int(row[3]))
        candidate = (order.order_id, order.signal_id, order.code, baseline.quantity)
        if existing != candidate:
            raise LivePositionBaselineConflictError(
                "execution_key is already bound to a different position baseline"
            )
        return LivePositionBaseline(code=existing[2], quantity=existing[3])

    def get_required(self, execution_key: str) -> LivePositionBaseline:
        key = self._required(execution_key, "execution_key")
        try:
            with self._connect() as connection:
                row = connection.execute(
                    f"SELECT code, quantity FROM {self.TABLE_NAME} WHERE execution_key = ?",
                    (key,),
                ).fetchone()
        except sqlite3.Error as exc:
            raise RuntimeError("Could not read live position baseline.") from exc
        if row is None:
            raise RuntimeError(f"Live position baseline does not exist: {key}")
        return LivePositionBaseline(code=str(row[0]), quantity=int(row[1]))

    def _initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self.TABLE_NAME} (
                    execution_key TEXT PRIMARY KEY,
                    order_id TEXT NOT NULL,
                    signal_id TEXT NOT NULL,
                    code TEXT NOT NULL,
                    quantity INTEGER NOT NULL CHECK (quantity >= 0)
                )
                """
            )
            connection.commit()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=30.0)
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    @staticmethod
    def _required(value: str, name: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError(f"{name} is required")
        return normalized


class _SubmissionCoordinator(Protocol):
    def submit(self, *, execution_key: str, order: TradeOrder, trading_date): ...


class LiveExecutionTrackingFlow:
    """Join durable baseline, activated submission, and read-only verification."""

    def __init__(
        self,
        *,
        baseline_repository: SQLiteLivePositionBaselineRepository,
        position_consistency_service: LiveExecutionPositionConsistencyService,
        submission_coordinator: _SubmissionCoordinator,
        submitted_lifecycle: LiveSubmittedExecutionLifecycle,
    ) -> None:
        self.baseline_repository = baseline_repository
        self.position_consistency_service = position_consistency_service
        self.submission_coordinator = submission_coordinator
        self.submitted_lifecycle = submitted_lifecycle

    def submit(
        self,
        *,
        execution_key: str,
        order: TradeOrder,
        trading_date,
        required_baseline_quantity: int | None = None,
    ) -> LiveExecutionTrackingResult:
        # This read must complete before the coordinator can reach transport.
        baseline = self.position_consistency_service.capture_baseline(order)
        if required_baseline_quantity is not None:
            if required_baseline_quantity < 0:
                raise ValueError("required_baseline_quantity must be non-negative")
            if baseline.quantity != required_baseline_quantity:
                raise LivePositionBaselineConflictError(
                    "fresh pre-submission live position changed after exit planning; "
                    "submission is blocked and the exit must be replanned"
                )
        durable = self.baseline_repository.save_once(
            execution_key, order=order, baseline=baseline
        )
        submission = self.submission_coordinator.submit(
            execution_key=execution_key,
            order=order,
            trading_date=trading_date,
        )
        mapping = {
            ActivatedLiveSubmissionDecision.TRANSPORT_BLOCKED: LiveExecutionTrackingDecision.SUBMISSION_BLOCKED,
            ActivatedLiveSubmissionDecision.SUBMITTED: LiveExecutionTrackingDecision.SUBMITTED,
            ActivatedLiveSubmissionDecision.UNKNOWN: LiveExecutionTrackingDecision.SUBMISSION_UNKNOWN,
        }
        return LiveExecutionTrackingResult(
            execution_key=execution_key,
            decision=mapping[submission.decision],
            baseline=durable,
            submission=submission,
            detail="pre-submission real-position baseline was durably captured before transport",
        )

    def reconcile(self, *, execution_key: str, order: TradeOrder) -> LiveExecutionTrackingResult:
        baseline = self.baseline_repository.get_required(execution_key)
        if baseline.code != order.code:
            raise LivePositionBaselineConflictError("stored baseline does not match order code")

        lifecycle = self.submitted_lifecycle.reconcile(execution_key)
        consistency = self.position_consistency_service.verify(
            order=order,
            baseline=baseline,
            reconciliation=lifecycle.reconciliation,
        )
        if consistency.decision is LiveExecutionPositionConsistencyDecision.UNKNOWN:
            decision = LiveExecutionTrackingDecision.UNKNOWN
        elif consistency.decision is LiveExecutionPositionConsistencyDecision.MISMATCH:
            decision = LiveExecutionTrackingDecision.POSITION_MISMATCH
        elif lifecycle.decision.value == "working":
            decision = LiveExecutionTrackingDecision.WORKING_CONSISTENT
        elif lifecycle.decision.value == "partially_filled":
            decision = LiveExecutionTrackingDecision.PARTIALLY_FILLED_CONSISTENT
        elif lifecycle.decision.value == "filled":
            decision = LiveExecutionTrackingDecision.FILLED_CONSISTENT
        else:
            decision = LiveExecutionTrackingDecision.TERMINATED_CONSISTENT

        return LiveExecutionTrackingResult(
            execution_key=execution_key,
            decision=decision,
            baseline=baseline,
            lifecycle=lifecycle,
            consistency=consistency,
            detail=(
                "broker execution and authoritative real position were reconciled "
                "against the durable pre-submission baseline"
            ),
        )
