"""PaperTradingScheduleStatusReaderのテスト。"""

import json
from pathlib import Path

from app.dashboard.paper_trading_schedule_status_reader import (
    PaperTradingScheduleStatusReader,
)


def test_reader_returns_missing_state(
    tmp_path: Path,
) -> None:
    payload = PaperTradingScheduleStatusReader(
        tmp_path / "missing.json"
    ).read()

    assert not payload["available"]
    assert payload["state"] == "not_started"


def test_reader_loads_status(
    tmp_path: Path,
) -> None:
    path = tmp_path / "status.json"
    path.write_text(
        json.dumps(
            {
                "state": "running",
                "enabled": True,
                "settings": {
                    "start_at": "08:45",
                },
            }
        ),
        encoding="utf-8",
    )

    payload = PaperTradingScheduleStatusReader(
        path
    ).read()

    assert payload["available"]
    assert payload["state"] == "running"
    assert payload["settings"]["start_at"] == "08:45"
