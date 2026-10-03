"""Fail-closed runtime safety-state provider for locked live execution.

Phase 6-C Step 4B-1 bridges the real three-way reconciliation report and the
latest in-memory FaultToleranceAttempt into the already-tested
LiveOrderSafetySnapshot contract.

No broker adapter, network transport, Paper runtime, or order submission path
is introduced here.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Protocol

from app.live.live_order_safety import (
    FaultToleranceAttemptLike,
    LiveOrderSafetySnapshot,
    ThreeWayReconciliationLike,
    safety_snapshot_from_states,
)


class ThreeWayReportProvider(Protocol):
    def __call__(self) -> ThreeWayReconciliationLike | None: ...


class FaultToleranceAttemptProvider(Protocol):
    def __call__(self) -> FaultToleranceAttemptLike | None: ...


NowProvider = Callable[[], datetime]


class LiveRuntimeSafetyStateProvider:
    """Return a fresh live safety snapshot or a fail-closed blocked snapshot."""

    def __init__(
        self,
        *,
        reconciliation_report_provider: ThreeWayReportProvider,
        fault_tolerance_attempt_provider: FaultToleranceAttemptProvider,
        maximum_reconciliation_age: timedelta = timedelta(minutes=2),
        maximum_future_skew: timedelta = timedelta(seconds=5),
        now_provider: NowProvider | None = None,
    ) -> None:
        if maximum_reconciliation_age <= timedelta(0):
            raise ValueError("maximum_reconciliation_age must be positive.")
        if maximum_future_skew < timedelta(0):
            raise ValueError("maximum_future_skew must not be negative.")

        self.reconciliation_report_provider = reconciliation_report_provider
        self.fault_tolerance_attempt_provider = fault_tolerance_attempt_provider
        self.maximum_reconciliation_age = maximum_reconciliation_age
        self.maximum_future_skew = maximum_future_skew
        self.now_provider = (
            now_provider
            if now_provider is not None
            else lambda: datetime.now(timezone.utc)
        )

    def __call__(self) -> LiveOrderSafetySnapshot:
        now = self._current_time()

        try:
            report = self.reconciliation_report_provider()
        except Exception:
            return self._blocked(
                now=now,
                state="reconciliation_unavailable",
            )

        if report is None:
            return self._blocked(
                now=now,
                state="reconciliation_missing",
            )

        generated_at = getattr(report, "generated_at", None)
        if not isinstance(generated_at, datetime) or generated_at.tzinfo is None:
            return self._blocked(
                now=now,
                state="reconciliation_timestamp_invalid",
            )

        report_time = generated_at.astimezone(timezone.utc)
        if report_time > now + self.maximum_future_skew:
            return self._blocked(
                now=now,
                state="reconciliation_from_future",
            )

        if now - report_time > self.maximum_reconciliation_age:
            return self._blocked(
                now=now,
                state="reconciliation_stale",
            )

        try:
            attempt = self.fault_tolerance_attempt_provider()
        except Exception:
            return self._blocked(
                now=now,
                state="fault_tolerance_unavailable",
            )

        try:
            return safety_snapshot_from_states(
                reconciliation_report=report,
                fault_tolerance_attempt=attempt,
            )
        except Exception:
            return self._blocked(
                now=now,
                state="safety_bridge_error",
            )

    @staticmethod
    def _blocked(
        *,
        now: datetime,
        state: str,
    ) -> LiveOrderSafetySnapshot:
        return LiveOrderSafetySnapshot(
            safe_stop_active=True,
            reconciliation_consistent=False,
            reconciliation_state=state,
            evaluated_at=now,
        )

    def _current_time(self) -> datetime:
        current = self.now_provider()
        if current.tzinfo is None:
            raise ValueError("now_provider must return a timezone-aware datetime.")
        return current.astimezone(timezone.utc)
