"""Dynamic WatchlistのAutonomous Validator連携テスト。"""

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from app.runtime.autonomous_operation_validator import (
    AutonomousOperationValidator,
)


NOW = datetime(2026, 8, 3, tzinfo=timezone.utc)


def write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload),
        encoding="utf-8",
    )


def test_completed_dynamic_watchlist_passes(
    tmp_path: Path,
) -> None:
    service = tmp_path / "service.json"
    paper = tmp_path / "paper.json"
    daily = tmp_path / "daily.json"
    dynamic = tmp_path / "dynamic.json"
    watchlist = tmp_path / "watchlist.txt"
    database = tmp_path / "katana.db"

    write(
        service,
        {
            "service_state": "healthy",
            "components": [
                {"name": "dashboard", "enabled": True, "state": "running"},
                {"name": "daily_report_scheduler", "enabled": True, "state": "running"},
                {"name": "paper_trading_scheduler", "enabled": True, "state": "running"},
                {"name": "paper_trading", "enabled": False, "state": "disabled"},
            ],
        },
    )
    write(paper, {"enabled": True, "state": "before_start"})
    write(daily, {"enabled": True, "state": "waiting"})
    write(
        dynamic,
        {
            "enabled": True,
            "state": "completed",
            "business_day": True,
            "selected_count": 5,
            "applied": True,
        },
    )
    watchlist.write_text(
        "6758\n7203\n9432\n8306\n9984\n",
        encoding="utf-8",
    )
    database.write_bytes(b"db")

    report = AutonomousOperationValidator(
        service_status_path=service,
        paper_schedule_status_path=paper,
        daily_report_schedule_status_path=daily,
        dynamic_watchlist_schedule_status_path=dynamic,
        watchlist_path=watchlist,
        database_path=database,
        now_provider=lambda: NOW,
        readiness_runner=lambda *_args, **_kwargs: SimpleNamespace(
            returncode=0,
            stdout="READY",
            stderr="",
        ),
    ).evaluate()

    check = next(
        item
        for item in report.checks
        if item.key == "dynamic_watchlist_schedule"
    )

    assert check.level.value == "pass"
