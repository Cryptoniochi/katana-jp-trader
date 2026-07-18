"""DashboardJsonSnapshotReaderのテスト。"""

import json
from datetime import datetime, timezone

from app.dashboard.dashboard_snapshot_file import (
    DashboardJsonSnapshotReader,
)


NOW = datetime(
    2026,
    7,
    18,
    0,
    0,
    tzinfo=timezone.utc,
)


def test_reader_returns_saved_snapshot(tmp_path) -> None:
    path = tmp_path / "dashboard.json"
    path.write_text(
        json.dumps(
            {
                "generated_at": NOW.isoformat(),
                "complete": True,
                "partial": False,
                "errors": [],
                "portfolio": None,
            }
        ),
        encoding="utf-8",
    )
    reader = DashboardJsonSnapshotReader(
        snapshot_path=path,
        now_provider=lambda: NOW,
    )

    payload = reader.create_snapshot()

    assert payload["complete"] is True
    assert payload["generated_at"] == NOW.isoformat()
    assert payload["broker"] is None


def test_reader_returns_partial_snapshot_when_missing(
    tmp_path,
) -> None:
    reader = DashboardJsonSnapshotReader(
        snapshot_path=tmp_path / "missing.json",
        now_provider=lambda: NOW,
    )

    payload = reader.create_snapshot()

    assert payload["partial"] is True
    assert payload["complete"] is False
    assert payload["errors"][0]["component"] == (
        "dashboard_snapshot_file"
    )


def test_reader_handles_invalid_json(tmp_path) -> None:
    path = tmp_path / "dashboard.json"
    path.write_text(
        "{invalid",
        encoding="utf-8",
    )
    reader = DashboardJsonSnapshotReader(
        snapshot_path=path,
        now_provider=lambda: NOW,
    )

    payload = reader.create_snapshot()

    assert payload["partial"] is True
    assert "読み込めません" in (
        payload["errors"][0]["error_message"]
    )
