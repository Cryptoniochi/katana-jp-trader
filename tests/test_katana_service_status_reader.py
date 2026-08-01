"""KatanaServiceStatusReaderのテスト。"""

import json
from datetime import datetime, timezone
from pathlib import Path

from app.dashboard.katana_service_status_reader import (
    KatanaServiceStatusReader,
)


NOW = datetime(
    2026,
    8,
    1,
    0,
    0,
    10,
    tzinfo=timezone.utc,
)


def test_reader_returns_empty_when_missing(
    tmp_path: Path,
) -> None:
    payload = KatanaServiceStatusReader(
        tmp_path / "missing.json",
        now_provider=lambda: NOW,
    ).read()

    assert not payload["available"]
    assert payload["service_state"] == "not_running"
    assert payload["components"] == []


def test_reader_loads_service_status(
    tmp_path: Path,
) -> None:
    path = tmp_path / "status.json"
    path.write_text(
        json.dumps(
            {
                "generated_at": (
                    "2026-08-01T00:00:00+00:00"
                ),
                "service_state": "healthy",
                "kabu_station_readiness": "ready",
                "components": [
                    {
                        "name": "dashboard",
                        "state": "running",
                        "enabled": True,
                        "process_id": 3120,
                        "restart_count": 0,
                        "last_exit_code": None,
                        "started_at": None,
                        "updated_at": (
                            "2026-08-01T00:00:00+00:00"
                        ),
                        "message": None,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    payload = KatanaServiceStatusReader(
        path,
        stale_after_seconds=30,
        now_provider=lambda: NOW,
    ).read()

    assert payload["available"]
    assert not payload["stale"]
    assert payload["service_state"] == "healthy"
    assert payload["source_service_state"] == "healthy"
    assert payload["kabu_station_readiness"] == "ready"
    assert payload["components"][0][
        "process_id"
    ] == 3120
