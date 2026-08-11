"""WatchlistExecutionIntegrityStatusReader tests."""

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from app.dashboard.watchlist_execution_integrity_status_reader import (
    WatchlistExecutionIntegrityStatusReader,
)


TOKYO = ZoneInfo("Asia/Tokyo")


def _today() -> str:
    return datetime.now(TOKYO).date().isoformat()


def test_reader_returns_not_yet_audited_when_report_missing(
    tmp_path: Path,
) -> None:
    reader = WatchlistExecutionIntegrityStatusReader(
        tmp_path / "missing.json"
    )

    payload = reader.read()

    assert payload["available"] is False
    assert payload["state"] == "not_yet_audited"
    assert payload["symbols"] == []


def test_reader_returns_pass_for_today_success(
    tmp_path: Path,
) -> None:
    report = tmp_path / "integrity.json"
    report.write_text(
        json.dumps(
            {
                "generated_at": "2026-08-12T06:01:00+00:00",
                "trading_date": _today(),
                "integrity_ok": True,
                "trace_available": True,
                "selected_count": 3,
                "loaded_count": 3,
                "monitored_count": 3,
                "signal_count": 1,
                "execution_count": 1,
                "selected_not_loaded_codes": [],
                "loaded_not_monitored_codes": [],
                "monitored_not_loaded_codes": [],
                "orphan_signal_codes": [],
                "orphan_execution_codes": [],
                "symbols": [
                    {
                        "code": "8306",
                        "selected": True,
                        "loaded": True,
                        "monitored": True,
                        "signal_count": 1,
                        "execution_count": 1,
                        "status": "executed",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    payload = WatchlistExecutionIntegrityStatusReader(
        report
    ).read()

    assert payload["available"] is True
    assert payload["state"] == "pass"
    assert payload["selected_count"] == 3
    assert payload["symbols"][0]["code"] == "8306"


def test_reader_returns_fail_for_today_mismatch(
    tmp_path: Path,
) -> None:
    report = tmp_path / "integrity.json"
    report.write_text(
        json.dumps(
            {
                "trading_date": _today(),
                "integrity_ok": False,
                "selected_not_loaded_codes": ["6758"],
                "symbols": [
                    {
                        "code": "6758",
                        "selected": True,
                        "loaded": False,
                        "monitored": False,
                        "signal_count": 0,
                        "execution_count": 0,
                        "status": "not_loaded",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    payload = WatchlistExecutionIntegrityStatusReader(
        report
    ).read()

    assert payload["available"] is True
    assert payload["state"] == "fail"
    assert payload["selected_not_loaded_codes"] == ["6758"]


def test_reader_treats_previous_day_as_not_yet_audited(
    tmp_path: Path,
) -> None:
    report = tmp_path / "integrity.json"
    report.write_text(
        json.dumps(
            {
                "trading_date": "2000-01-01",
                "integrity_ok": True,
                "symbols": [],
            }
        ),
        encoding="utf-8",
    )

    payload = WatchlistExecutionIntegrityStatusReader(
        report
    ).read()

    assert payload["available"] is True
    assert payload["state"] == "not_yet_audited"


def test_reader_returns_unavailable_for_invalid_json(
    tmp_path: Path,
) -> None:
    report = tmp_path / "integrity.json"
    report.write_text("{broken", encoding="utf-8")

    payload = WatchlistExecutionIntegrityStatusReader(
        report
    ).read()

    assert payload["available"] is False
    assert payload["state"] == "unavailable"
