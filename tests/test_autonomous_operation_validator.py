"""AutonomousOperationValidatorのテスト。"""

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from app.runtime.autonomous_operation_validator import (
    AutonomousOperationValidator,
)


NOW = datetime(
    2026,
    8,
    1,
    tzinfo=timezone.utc,
)


def write_json(
    path: Path,
    payload: dict,
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    path.write_text(
        json.dumps(payload),
        encoding="utf-8",
    )


def create_validator(
    tmp_path: Path,
    *,
    readiness_code: int = 0,
) -> AutonomousOperationValidator:
    service = tmp_path / "service.json"
    paper = tmp_path / "paper.json"
    daily = tmp_path / "daily.json"
    watchlist = tmp_path / "watchlist.txt"
    database = tmp_path / "katana.db"

    write_json(
        service,
        {
            "service_state": "healthy",
            "service_started_at": NOW.isoformat(),
            "uptime_seconds": 60.0,
            "kabu_station_readiness": "connected",
            "components": [
                {
                    "name": "dashboard",
                    "enabled": True,
                    "state": "running",
                },
                {
                    "name": "daily_report_scheduler",
                    "enabled": True,
                    "state": "running",
                },
                {
                    "name": "paper_trading_scheduler",
                    "enabled": True,
                    "state": "running",
                },
                {
                    "name": "paper_trading",
                    "enabled": False,
                    "state": "disabled",
                },
            ],
        },
    )
    write_json(
        paper,
        {
            "enabled": True,
            "state": "closed_day",
            "business_day": False,
        },
    )
    write_json(
        daily,
        {
            "enabled": True,
            "state": "closed_day",
            "business_day": False,
        },
    )
    watchlist.write_text(
        "7203\n6758\n",
        encoding="utf-8",
    )
    database.write_bytes(b"db")

    return AutonomousOperationValidator(
        service_status_path=service,
        paper_schedule_status_path=paper,
        daily_report_schedule_status_path=daily,
        watchlist_path=watchlist,
        database_path=database,
        now_provider=lambda: NOW,
        readiness_runner=(
            lambda *_args, **_kwargs: SimpleNamespace(
                returncode=readiness_code,
                stdout="Overall READY",
                stderr="",
            )
        ),
    )


def test_validator_reports_ready(
    tmp_path: Path,
) -> None:
    report = create_validator(
        tmp_path
    ).evaluate()

    assert report.overall_state == "ready"
    assert report.ready_for_next_business_day


def test_failed_production_readiness_blocks_operation(
    tmp_path: Path,
) -> None:
    report = create_validator(
        tmp_path,
        readiness_code=1,
    ).evaluate()

    assert report.overall_state == "blocked"
    assert not report.ready_for_next_business_day


def test_watchlist_over_fifty_blocks_operation(
    tmp_path: Path,
) -> None:
    validator = create_validator(tmp_path)
    validator.watchlist_path.write_text(
        "\n".join(
            f"{1000 + index:04d}"
            for index in range(51)
        ),
        encoding="utf-8",
    )

    report = validator.evaluate()
    check = next(
        item
        for item in report.checks
        if item.key == "watchlist"
    )

    assert check.level.value == "fail"
    assert not report.ready_for_next_business_day
