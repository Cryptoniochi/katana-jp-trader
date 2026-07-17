"""耐障害性モデルのテスト。"""

from datetime import datetime, timezone

import pytest

from app.supervisor.fault_tolerance_models import (
    FaultToleranceAttempt,
    FaultToleranceDecision,
    FaultTolerancePolicy,
)
from app.supervisor.supervisor_models import (
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


def supervisor_snapshot(
    status: SupervisorStatus,
) -> SupervisorSnapshot:
    return SupervisorSnapshot(
        worker_name="live-worker",
        status=status,
        started_at=NOW,
        checked_at=NOW,
        last_heartbeat_at=NOW,
        last_restart_at=None,
        restart_count=0,
        stop_reason=(
            SupervisorStopReason.ERROR
            if status is SupervisorStatus.FAILED
            else None
        ),
    )


def test_policy_rejects_non_positive_failure_limit() -> None:
    with pytest.raises(ValueError):
        FaultTolerancePolicy(
            maximum_consecutive_recovery_failures=0
        )


def test_attempt_requires_next_action_for_deferred() -> None:
    snapshot = supervisor_snapshot(
        SupervisorStatus.RUNNING
    )

    with pytest.raises(
        ValueError,
        match="次回実行日時",
    ):
        FaultToleranceAttempt(
            attempt_number=1,
            checked_at=NOW,
            decision=FaultToleranceDecision.DEFERRED,
            supervisor_before=snapshot,
            supervisor_after=snapshot,
            recovery_result=None,
            consecutive_failure_count=0,
            next_action_at=None,
            message="deferred",
        )


def test_safe_stop_requires_attention() -> None:
    snapshot = supervisor_snapshot(
        SupervisorStatus.FAILED
    )

    attempt = FaultToleranceAttempt(
        attempt_number=1,
        checked_at=NOW,
        decision=FaultToleranceDecision.SAFE_STOP,
        supervisor_before=snapshot,
        supervisor_after=snapshot,
        recovery_result=None,
        consecutive_failure_count=3,
        next_action_at=None,
        message="safe stop",
    )

    assert attempt.requires_attention
    assert attempt.is_successful is False
