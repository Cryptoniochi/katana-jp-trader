"""Supervisor共通モデルのテスト。"""

from datetime import datetime, timezone

import pytest

from app.supervisor.supervisor_models import (
    RestartDecision,
    SupervisorPolicy,
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


def test_policy_rejects_invalid_values() -> None:
    with pytest.raises(ValueError):
        SupervisorPolicy(
            heartbeat_timeout_seconds=0
        )

    with pytest.raises(ValueError):
        SupervisorPolicy(
            restart_cooldown_seconds=-1
        )

    with pytest.raises(ValueError):
        SupervisorPolicy(
            maximum_restart_count=-1
        )


def test_snapshot_calculates_uptime_and_heartbeat_age() -> None:
    snapshot = SupervisorSnapshot(
        worker_name=" live-worker ",
        status=SupervisorStatus.RUNNING,
        started_at=NOW,
        checked_at=NOW.replace(second=30),
        last_heartbeat_at=NOW.replace(second=20),
        last_restart_at=None,
        restart_count=0,
        stop_reason=None,
    )

    assert snapshot.worker_name == "live-worker"
    assert snapshot.uptime_seconds == 30.0
    assert snapshot.heartbeat_age_seconds == 10.0
    assert snapshot.is_running
    assert snapshot.requires_attention is False


def test_failed_snapshot_requires_stop_reason() -> None:
    with pytest.raises(
        ValueError,
        match="停止理由",
    ):
        SupervisorSnapshot(
            worker_name="worker",
            status=SupervisorStatus.FAILED,
            started_at=NOW,
            checked_at=NOW,
            last_heartbeat_at=NOW,
            last_restart_at=None,
            restart_count=0,
            stop_reason=None,
        )


def test_restart_decision_validates_required_fields() -> None:
    with pytest.raises(ValueError):
        RestartDecision(
            should_restart=True,
            reason=None,
            next_restart_at=NOW,
        )

    with pytest.raises(ValueError):
        RestartDecision(
            should_restart=False,
            reason=None,
            next_restart_at=NOW,
        )
