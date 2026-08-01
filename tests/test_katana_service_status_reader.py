"""KatanaServiceStatusReaderのテスト。"""

import json
from pathlib import Path

from app.dashboard.katana_service_status_reader import (
    KatanaServiceStatusReader,
)


def test_reader_returns_empty_when_missing(
    tmp_path: Path,
) -> None:
    payload = KatanaServiceStatusReader(
        tmp_path / "missing.json"
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
        path
    ).read()

    assert payload["available"]
    assert payload["service_state"] == "healthy"
    assert payload["kabu_station_readiness"] == "ready"
    assert payload["components"][0][
        "process_id"
    ] == 3120
