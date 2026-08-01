"""Service StatusのUptime/Event読込テスト。"""

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
    1,
    0,
    5,
    tzinfo=timezone.utc,
)


def test_reader_includes_uptime_and_events(
    tmp_path: Path,
) -> None:
    path = tmp_path / "status.json"
    path.write_text(
        json.dumps(
            {
                "generated_at": (
                    "2026-08-01T01:00:00+00:00"
                ),
                "service_state": "healthy",
                "kabu_station_readiness": "connected",
                "service_started_at": (
                    "2026-08-01T00:00:00+00:00"
                ),
                "uptime_seconds": 3600,
                "components": [],
                "recent_events": [
                    {
                        "occurred_at": (
                            "2026-08-01T00:30:00+00:00"
                        ),
                        "event_type": (
                            "restart_completed"
                        ),
                        "component": "dashboard",
                        "message": "dashboard started",
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

    assert payload["uptime_seconds"] == 3600
    assert payload["recent_events"][0][
        "component"
    ] == "dashboard"
