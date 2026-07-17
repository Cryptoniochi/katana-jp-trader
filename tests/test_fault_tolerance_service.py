"""FaultToleranceServiceのテスト。"""

from datetime import datetime, timedelta, timezone

from app.live.recovery_models import (
    RecoveryResult,
    RecoveryStatus,
)
from app.supervisor.fault_tolerance_models import (
    FaultToleranceDecision,
    FaultTolerancePolicy,
)
from app.supervisor.fault_tolerance_service import (
    FaultToleranceService,
)
from app.supervisor.supervisor_models import (
    RestartDecision,
    SupervisorSnapshot,
    SupervisorStatus,
    SupervisorStopReason,
)


NOW = datetime(
    2026,
    7,
    18,
    0,
    0,
    tzinfo=timezone.utc,
)


def snapshot(
    status: SupervisorStatus,
    *,
    restart_count: int = 0,
    stop_reason: SupervisorStopReason | None = None,
) -> SupervisorSnapshot:
    return SupervisorSnapshot(
        worker_name="live-worker",
        status=status,
        started_at=NOW,
        checked_at=NOW,
        last_heartbeat_at=NOW,
        last_restart_at=None,
        restart_count=restart_count,
        stop_reason=stop_reason,
    )


def recovery_result(
    status: RecoveryStatus,
) -> RecoveryResult:
    return RecoveryResult(
        status=status,
        steps=(),
        health_result=None,
        execution_result=None,
        portfolio_audit_report=None,
    )


class FakeSupervisor:
    def __init__(
        self,
        current: SupervisorSnapshot,
    ) -> None:
        self.current = current
        self.restart = RestartDecision(
            should_restart=False,
            reason=None,
            next_restart_at=None,
            message="no restart",
        )

    def check(self):
        return self.current

    def restart_decision(self):
        return self.restart

    def mark_restarted(self):
        self.current = snapshot(
            SupervisorStatus.RUNNING,
            restart_count=(
                self.current.restart_count + 1
            ),
        )
        return self.current

    def stop(
        self,
        *,
        reason,
        message=None,
    ):
        self.current = snapshot(
            SupervisorStatus.FAILED,
            restart_count=self.current.restart_count,
            stop_reason=reason,
        )
        return self.current


class FakeRecoveryManager:
    def __init__(self) -> None:
        self.result = recovery_result(
            RecoveryStatus.COMPLETED
        )
        self.error: Exception | None = None
        self.calls = 0

    def recover(
        self,
        *,
        continue_on_error=False,
    ):
        self.calls += 1

        if self.error is not None:
            raise self.error

        return self.result


def test_healthy_worker_requires_no_action() -> None:
    supervisor = FakeSupervisor(
        snapshot(SupervisorStatus.RUNNING)
    )
    recovery = FakeRecoveryManager()
    service = FaultToleranceService(
        supervisor=supervisor,
        recovery_manager=recovery,
        now_provider=lambda: NOW,
    )

    attempt = service.run_once()

    assert attempt.decision is (
        FaultToleranceDecision.NO_ACTION
    )
    assert recovery.calls == 0


def test_recovery_is_deferred_during_cooldown() -> None:
    supervisor = FakeSupervisor(
        snapshot(
            SupervisorStatus.FAILED,
            stop_reason=SupervisorStopReason.ERROR,
        )
    )
    supervisor.restart = RestartDecision(
        should_restart=True,
        reason=SupervisorStopReason.ERROR,
        next_restart_at=NOW + timedelta(seconds=30),
        message="restart later",
    )
    recovery = FakeRecoveryManager()
    service = FaultToleranceService(
        supervisor=supervisor,
        recovery_manager=recovery,
        now_provider=lambda: NOW,
    )

    attempt = service.run_once()

    assert attempt.decision is (
        FaultToleranceDecision.DEFERRED
    )
    assert attempt.next_action_at == (
        NOW + timedelta(seconds=30)
    )
    assert recovery.calls == 0


def test_successful_recovery_restarts_worker() -> None:
    supervisor = FakeSupervisor(
        snapshot(
            SupervisorStatus.FAILED,
            stop_reason=SupervisorStopReason.ERROR,
        )
    )
    supervisor.restart = RestartDecision(
        should_restart=True,
        reason=SupervisorStopReason.ERROR,
        next_restart_at=NOW,
        message="restart now",
    )
    recovery = FakeRecoveryManager()
    service = FaultToleranceService(
        supervisor=supervisor,
        recovery_manager=recovery,
        now_provider=lambda: NOW,
    )

    attempt = service.run_once()

    assert attempt.decision is (
        FaultToleranceDecision.RECOVERED
    )
    assert attempt.supervisor_after.status is (
        SupervisorStatus.RUNNING
    )
    assert attempt.consecutive_failure_count == 0
    assert recovery.calls == 1


def test_failed_recovery_is_recorded() -> None:
    supervisor = FakeSupervisor(
        snapshot(
            SupervisorStatus.FAILED,
            stop_reason=SupervisorStopReason.ERROR,
        )
    )
    supervisor.restart = RestartDecision(
        should_restart=True,
        reason=SupervisorStopReason.ERROR,
        next_restart_at=NOW,
        message="restart now",
    )
    recovery = FakeRecoveryManager()
    recovery.result = recovery_result(
        RecoveryStatus.COMPLETED_WITH_ERRORS
    )
    service = FaultToleranceService(
        supervisor=supervisor,
        recovery_manager=recovery,
        policy=FaultTolerancePolicy(
            maximum_consecutive_recovery_failures=2
        ),
        now_provider=lambda: NOW,
    )

    attempt = service.run_once()

    assert attempt.decision is (
        FaultToleranceDecision.RECOVERY_FAILED
    )
    assert attempt.consecutive_failure_count == 1
    assert len(service.history()) == 1


def test_consecutive_failures_trigger_safe_stop() -> None:
    supervisor = FakeSupervisor(
        snapshot(
            SupervisorStatus.FAILED,
            stop_reason=SupervisorStopReason.ERROR,
        )
    )
    supervisor.restart = RestartDecision(
        should_restart=True,
        reason=SupervisorStopReason.ERROR,
        next_restart_at=NOW,
        message="restart now",
    )
    recovery = FakeRecoveryManager()
    recovery.error = RuntimeError("recovery failed")
    service = FaultToleranceService(
        supervisor=supervisor,
        recovery_manager=recovery,
        policy=FaultTolerancePolicy(
            maximum_consecutive_recovery_failures=2
        ),
        now_provider=lambda: NOW,
    )

    first = service.run_once()
    second = service.run_once()

    assert first.decision is (
        FaultToleranceDecision.RECOVERY_FAILED
    )
    assert second.decision is (
        FaultToleranceDecision.SAFE_STOP
    )
    assert second.consecutive_failure_count == 2


def test_restart_limit_causes_safe_stop() -> None:
    supervisor = FakeSupervisor(
        snapshot(
            SupervisorStatus.FAILED,
            stop_reason=SupervisorStopReason.ERROR,
        )
    )
    supervisor.restart = RestartDecision(
        should_restart=False,
        reason=SupervisorStopReason.RESTART_LIMIT,
        next_restart_at=None,
        message="restart limit",
    )
    service = FaultToleranceService(
        supervisor=supervisor,
        recovery_manager=FakeRecoveryManager(),
        now_provider=lambda: NOW,
    )

    attempt = service.run_once()

    assert attempt.decision is (
        FaultToleranceDecision.SAFE_STOP
    )
    assert attempt.supervisor_after.stop_reason is (
        SupervisorStopReason.RESTART_LIMIT
    )
