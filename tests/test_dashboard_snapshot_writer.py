"""DashboardSnapshotWriterのテスト。"""

import json
from datetime import datetime, timezone

from app.dashboard.dashboard_snapshot_writer import (
    DashboardSnapshotWriter,
)


NOW = datetime(
    2026,
    7,
    18,
    0,
    0,
    tzinfo=timezone.utc,
)


def payload(
    *,
    complete: bool = True,
) -> dict:
    """テスト用Dashboard Payloadを作成する。"""

    return {
        "generated_at": NOW.isoformat(),
        "complete": complete,
        "partial": not complete,
        "errors": [],
        "system_health": None,
        "runtime_metrics": None,
        "runtime_resource": None,
        "portfolio": None,
        "orders": None,
        "live_summary": None,
        "broker": None,
        "message": "日本語テスト",
    }


def test_writer_creates_parent_and_json_file(
    tmp_path,
) -> None:
    output_path = (
        tmp_path
        / "reports"
        / "dashboard"
        / "dashboard.json"
    )
    writer = DashboardSnapshotWriter(
        output_path=output_path
    )

    result = writer.write(payload())

    assert output_path.exists()
    assert result.output_path == output_path
    assert result.generated_at == NOW
    assert result.size_bytes > 0

    saved = json.loads(
        output_path.read_text(encoding="utf-8")
    )
    assert saved["complete"] is True
    assert saved["message"] == "日本語テスト"


def test_writer_overwrites_existing_file_atomically(
    tmp_path,
) -> None:
    output_path = tmp_path / "dashboard.json"
    writer = DashboardSnapshotWriter(
        output_path=output_path
    )

    writer.write(payload(complete=False))
    writer.write(payload(complete=True))

    saved = json.loads(
        output_path.read_text(encoding="utf-8")
    )

    assert saved["complete"] is True
    assert saved["partial"] is False
    assert not (
        tmp_path / "dashboard.json.tmp"
    ).exists()


def test_writer_rejects_missing_generated_at(
    tmp_path,
) -> None:
    writer = DashboardSnapshotWriter(
        output_path=tmp_path / "dashboard.json"
    )

    value = payload()
    value.pop("generated_at")

    try:
        writer.write(value)
    except ValueError as error:
        assert "generated_at" in str(error)
    else:
        raise AssertionError(
            "generated_atなしのPayloadが受理されました。"
        )
