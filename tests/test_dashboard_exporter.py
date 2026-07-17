"""DashboardExporterのテスト。"""

import json
from datetime import datetime, timezone
from pathlib import Path

from app.dashboard.dashboard_exporter import (
    DashboardExporter,
)
from app.dashboard.dashboard_models import (
    DashboardBrokerStatus,
    DashboardSnapshot,
)


NOW = datetime(
    2026,
    7,
    18,
    0,
    0,
    0,
    123456,
    tzinfo=timezone.utc,
)


def snapshot() -> DashboardSnapshot:
    return DashboardSnapshot(
        generated_at=NOW,
        system_health=None,
        runtime_metrics=None,
        portfolio=None,
        orders=None,
        live_summary=None,
        broker=DashboardBrokerStatus(
            connected=True,
            name="paper",
        ),
        errors=(),
    )


def test_exporter_writes_latest_and_history(
    tmp_path: Path,
) -> None:
    exporter = DashboardExporter(
        output_directory=tmp_path,
    )

    result = exporter.export(snapshot())

    assert result.latest_path == (
        tmp_path / "dashboard.json"
    )
    assert result.history_path == (
        tmp_path
        / "dashboard_20260718T000000123456Z.json"
    )
    assert result.latest_path.is_file()
    assert result.history_path is not None
    assert result.history_path.is_file()
    assert result.bytes_written > 0

    latest_payload = json.loads(
        result.latest_path.read_text(
            encoding="utf-8"
        )
    )
    history_payload = json.loads(
        result.history_path.read_text(
            encoding="utf-8"
        )
    )

    assert latest_payload == history_payload
    assert latest_payload["broker"]["name"] == "paper"


def test_exporter_can_disable_history(
    tmp_path: Path,
) -> None:
    exporter = DashboardExporter(
        output_directory=tmp_path,
        latest_filename="latest.json",
        save_history=False,
    )

    result = exporter.export(snapshot())

    assert result.latest_path == (
        tmp_path / "latest.json"
    )
    assert result.history_path is None
    assert list(tmp_path.glob("*.json")) == [
        tmp_path / "latest.json"
    ]


def test_exporter_replaces_existing_latest(
    tmp_path: Path,
) -> None:
    latest = tmp_path / "dashboard.json"
    tmp_path.mkdir(
        parents=True,
        exist_ok=True,
    )
    latest.write_text(
        "old",
        encoding="utf-8",
    )
    exporter = DashboardExporter(
        output_directory=tmp_path,
        save_history=False,
    )

    exporter.export(snapshot())

    assert latest.read_text(
        encoding="utf-8"
    ) != "old"
    assert not (
        tmp_path / ".dashboard.json.tmp"
    ).exists()
