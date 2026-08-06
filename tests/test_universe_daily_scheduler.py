"""Universe Daily Schedulerのテスト。"""

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from app.market.market_calendar import TokyoMarketCalendar
from app.runtime.universe_daily_schedule_models import (
    UniverseDailyScheduleState,
)
from app.runtime.universe_daily_scheduler import (
    UniverseDailyScheduler,
)


def test_successful_collection_creates_marker(
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "daily.json"

    def run(_command, **_kwargs):
        report_path.write_text(
            json.dumps(
                {
                    "trading_date": "2026-08-06",
                    "requested_count": 100,
                    "collected_count": 95,
                    "success_ratio": 0.95,
                }
            ),
            encoding="utf-8",
        )
        return SimpleNamespace(returncode=0)

    scheduler = UniverseDailyScheduler(
        enabled=True,
        database_path=tmp_path / "katana.db",
        report_path=report_path,
        status_path=tmp_path / "status.json",
        marker_directory=tmp_path / "markers",
        calendar=TokyoMarketCalendar.with_custom_holidays([]),
        now_provider=lambda: datetime(
            2026,
            8,
            6,
            6,
            40,
            tzinfo=timezone.utc,
        ),
        command_runner=run,
    )

    status = scheduler.run_once()

    assert status.state is UniverseDailyScheduleState.COMPLETED
    assert status.collected_count == 95
    assert (
        tmp_path
        / "markers"
        / "2026-08-06.completed.json"
    ).exists()
