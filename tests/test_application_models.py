"""Application Lifecycleモデルのテスト。"""

from datetime import datetime, timezone

import pytest

from app.application.application_models import (
    ApplicationReport,
    ApplicationSnapshot,
    ApplicationState,
    ApplicationStopReason,
)


NOW = datetime(
    2026,
    7,
    18,
    12,
    0,
    tzinfo=timezone.utc,
)


def test_created_snapshot_has_zero_uptime() -> None:
    snapshot = ApplicationSnapshot(
        application_name=" Project KATANA ",
        state=ApplicationState.CREATED,
        created_at=NOW,
        checked_at=NOW,
    )

    assert snapshot.application_name == "Project KATANA"
    assert snapshot.uptime_seconds == 0.0
    assert snapshot.is_running is False
    assert snapshot.is_terminal is False


def test_running_snapshot_calculates_uptime() -> None:
    snapshot = ApplicationSnapshot(
        application_name="Project KATANA",
        state=ApplicationState.RUNNING,
        created_at=NOW,
        checked_at=NOW.replace(minute=5),
        started_at=NOW,
    )

    assert snapshot.uptime_seconds == 300.0
    assert snapshot.is_running
    assert snapshot.is_terminal is False


def test_terminal_snapshot_requires_stop_information() -> None:
    with pytest.raises(
        ValueError,
        match="終了状態",
    ):
        ApplicationSnapshot(
            application_name="Project KATANA",
            state=ApplicationState.STOPPED,
            created_at=NOW,
            checked_at=NOW,
            started_at=NOW,
        )


def test_failed_report_cannot_be_graceful() -> None:
    snapshot = ApplicationSnapshot(
        application_name="Project KATANA",
        state=ApplicationState.FAILED,
        created_at=NOW,
        checked_at=NOW,
        started_at=NOW,
        stopping_at=NOW,
        stopped_at=NOW,
        stop_reason=ApplicationStopReason.ERROR,
    )

    with pytest.raises(
        ValueError,
        match="Graceful",
    ):
        ApplicationReport(
            snapshot=snapshot,
            graceful_shutdown=True,
        )
