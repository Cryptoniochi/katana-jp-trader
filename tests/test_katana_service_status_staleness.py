"""Service状態鮮度判定のテスト。"""

import json
from datetime import datetime, timedelta, timezone
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
    tzinfo=timezone.utc,
)


def write_status(
    path: Path,
    generated_at: datetime,
) -> None:
    path.write_text(
        json.dumps(
            {
                "generated_at": generated_at.isoformat(),
                "service_state": "healthy",
                "kabu_station_readiness": "not_checked",
                "components": [],
            }
        ),
        encoding="utf-8",
    )


def test_fresh_status_remains_healthy(
    tmp_path: Path,
) -> None:
    path = tmp_path / "status.json"
    write_status(
        path,
        NOW - timedelta(seconds=5),
    )

    payload = KatanaServiceStatusReader(
        path,
        stale_after_seconds=30,
        now_provider=lambda: NOW,
    ).read()

    assert not payload["stale"]
    assert payload["service_state"] == "healthy"


def test_old_status_becomes_stale(
    tmp_path: Path,
) -> None:
    path = tmp_path / "status.json"
    write_status(
        path,
        NOW - timedelta(seconds=31),
    )

    payload = KatanaServiceStatusReader(
        path,
        stale_after_seconds=30,
        now_provider=lambda: NOW,
    ).read()

    assert payload["stale"]
    assert payload["service_state"] == "stale"
    assert payload["source_service_state"] == "healthy"
