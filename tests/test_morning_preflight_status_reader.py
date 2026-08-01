"""MorningPreflightStatusReaderのテスト。"""

import json
from pathlib import Path

from app.dashboard.morning_preflight_status_reader import (
    MorningPreflightStatusReader,
)


def test_reader_combines_schedule_and_report(
    tmp_path: Path,
) -> None:
    schedule = tmp_path / "schedule.json"
    report = tmp_path / "report.json"

    schedule.write_text(
        json.dumps(
            {
                "generated_at": "2026-08-03T08:40:00+09:00",
                "target_date": "2026-08-03",
                "state": "completed",
                "last_attempt_at": "2026-08-03T08:40:00+09:00",
                "last_exit_code": 0,
                "message": "completed",
            }
        ),
        encoding="utf-8",
    )
    report.write_text(
        json.dumps(
            {
                "overall_state": "ready",
                "ready_for_next_business_day": True,
                "checks": [
                    {
                        "key": "service",
                        "label": "KATANA Service",
                        "level": "pass",
                        "message": "healthy",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    payload = MorningPreflightStatusReader(
        schedule_status_path=schedule,
        operation_report_path=report,
    ).read()

    assert payload["available"]
    assert payload["schedule_state"] == "completed"
    assert payload["overall_state"] == "ready"
    assert payload["ready_for_trading"]
    assert payload["checks"][0]["level"] == "pass"


def test_reader_returns_unavailable_without_files(
    tmp_path: Path,
) -> None:
    payload = MorningPreflightStatusReader(
        schedule_status_path=tmp_path / "missing1.json",
        operation_report_path=tmp_path / "missing2.json",
    ).read()

    assert not payload["available"]
    assert not payload["ready_for_trading"]
