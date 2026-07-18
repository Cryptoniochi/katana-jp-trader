"""Runtime Health Monitorモデルのテスト。"""

from datetime import datetime, timezone

import pytest

from app.runtime.runtime_health_monitor_models import (
    RuntimeActivitySnapshot,
    RuntimeHealthMonitorPolicy,
)


NOW = datetime(
    2026,
    7,
    18,
    0,
    0,
    tzinfo=timezone.utc,
)


def test_policy_validates_threshold_order() -> None:
    with pytest.raises(
        ValueError,
        match="重大秒数",
    ):
        RuntimeHealthMonitorPolicy(
            heartbeat_warning_seconds=120.0,
            heartbeat_critical_seconds=60.0,
        )


def test_running_snapshot_requires_started_at() -> None:
    with pytest.raises(
        ValueError,
        match="開始日時",
    ):
        RuntimeActivitySnapshot(
            checked_at=NOW,
            running=True,
            started_at=None,
            last_heartbeat_at=None,
            last_cycle_at=None,
        )
