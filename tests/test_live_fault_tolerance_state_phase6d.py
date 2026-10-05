"""Phase 6-D tests for the read-only fault-tolerance state bridge."""

from __future__ import annotations

from datetime import datetime, timezone

from app.live.live_fault_tolerance_state import LatestFaultToleranceAttemptProvider
from app.supervisor.fault_tolerance_models import (
    FaultToleranceAttempt,
    FaultToleranceDecision,
)
from app.supervisor.supervisor_models import (
    SupervisorSnapshot,
    SupervisorStatus,
)


NOW = datetime(2026, 10, 5, 5, 0, tzinfo=timezone.utc)


def _snapshot() -> SupervisorSnapshot:
    return SupervisorSnapshot(
        worker_name="live-worker",
        status=SupervisorStatus.RUNNING,
        started_at=NOW,
        checked_at=NOW,
        last_heartbeat_at=NOW,
        last_restart_at=None,
        restart_count=0,
        stop_reason=None,
    )


def _attempt(number: int, decision: FaultToleranceDecision) -> FaultToleranceAttempt:
    snapshot = _snapshot()
    return FaultToleranceAttempt(
        attempt_number=number,
        checked_at=NOW,
        decision=decision,
        supervisor_before=snapshot,
        supervisor_after=snapshot,
        recovery_result=None,
        consecutive_failure_count=0,
        next_action_at=None,
        message="test",
    )


class FakeFaultToleranceService:
    def __init__(self, attempts: tuple[FaultToleranceAttempt, ...]) -> None:
        self.attempts = attempts
        self.history_calls = 0

    def history(self) -> tuple[FaultToleranceAttempt, ...]:
        self.history_calls += 1
        return self.attempts


def test_empty_history_returns_none() -> None:
    service = FakeFaultToleranceService(())
    provider = LatestFaultToleranceAttemptProvider(service)

    assert provider() is None
    assert service.history_calls == 1


def test_latest_attempt_is_returned_without_running_service() -> None:
    first = _attempt(1, FaultToleranceDecision.NO_ACTION)
    latest = _attempt(2, FaultToleranceDecision.SAFE_STOP)
    service = FakeFaultToleranceService((first, latest))
    provider = LatestFaultToleranceAttemptProvider(service)

    assert provider() is latest
    assert service.history_calls == 1


def test_construction_does_not_evaluate_service() -> None:
    service = FakeFaultToleranceService(())
    LatestFaultToleranceAttemptProvider(service)

    assert service.history_calls == 0


def test_provider_exposes_safe_stop_unchanged() -> None:
    safe_stop = _attempt(3, FaultToleranceDecision.SAFE_STOP)
    provider = LatestFaultToleranceAttemptProvider(
        FakeFaultToleranceService((safe_stop,))
    )

    result = provider()

    assert result is safe_stop
    assert result is not None
    assert result.decision is FaultToleranceDecision.SAFE_STOP
