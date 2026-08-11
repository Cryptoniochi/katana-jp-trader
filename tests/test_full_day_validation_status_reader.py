"""FullDayValidationStatusReader tests。"""

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from app.dashboard.full_day_validation_status_reader import (
    FullDayValidationStatusReader,
)


TOKYO = ZoneInfo("Asia/Tokyo")


def _today() -> str:
    return datetime.now(TOKYO).date().isoformat()


def test_missing_report_is_not_yet_validated(
    tmp_path: Path,
) -> None:
    payload = FullDayValidationStatusReader(
        tmp_path / "missing.json"
    ).read()

    assert payload["available"] is False
    assert payload["state"] == "not_yet_validated"


def test_today_pass_report_is_pass(
    tmp_path: Path,
) -> None:
    path = tmp_path / "validation.json"
    path.write_text(
        json.dumps(
            {
                "trading_date": _today(),
                "passed": True,
                "failed_check_count": 0,
                "checks": [
                    {
                        "key": "runtime_completed",
                        "label": "Runtime completed",
                        "passed": True,
                        "message": "Runtime completed normally.",
                    }
                ],
                "runtime": {"state": "completed"},
                "integrity": {"integrity_ok": True},
                "daily_summary": {"available": True},
                "daily_report": {"status": "complete"},
            }
        ),
        encoding="utf-8",
    )

    payload = FullDayValidationStatusReader(
        path
    ).read()

    assert payload["available"] is True
    assert payload["state"] == "pass"
    assert payload["failed_check_count"] == 0


def test_today_failed_report_is_fail(
    tmp_path: Path,
) -> None:
    path = tmp_path / "validation.json"
    path.write_text(
        json.dumps(
            {
                "trading_date": _today(),
                "passed": False,
                "failed_check_count": 1,
                "checks": [
                    {
                        "key": "end_of_day_positions",
                        "label": "End-of-day positions",
                        "passed": False,
                        "message": "remaining_position_count=1",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    payload = FullDayValidationStatusReader(
        path
    ).read()

    assert payload["state"] == "fail"
    assert payload["failed_check_count"] == 1


def test_previous_day_is_not_yet_validated(
    tmp_path: Path,
) -> None:
    path = tmp_path / "validation.json"
    path.write_text(
        json.dumps(
            {
                "trading_date": "2000-01-01",
                "passed": True,
                "checks": [],
            }
        ),
        encoding="utf-8",
    )

    payload = FullDayValidationStatusReader(
        path
    ).read()

    assert payload["available"] is True
    assert payload["state"] == "not_yet_validated"


def test_invalid_json_is_unavailable(
    tmp_path: Path,
) -> None:
    path = tmp_path / "validation.json"
    path.write_text("{broken", encoding="utf-8")

    payload = FullDayValidationStatusReader(
        path
    ).read()

    assert payload["available"] is False
    assert payload["state"] == "unavailable"
