"""DailyReportReaderのテスト。"""

import json
from datetime import date
from pathlib import Path

import pytest

from app.dashboard.daily_report_reader import (
    DailyReportReadError,
    DailyReportReader,
)


def write_report(
    directory: Path,
    report_date: str,
    *,
    net_profit_loss: float,
) -> Path:
    directory.mkdir(
        parents=True,
        exist_ok=True,
    )
    path = directory / f"{report_date}.json"
    path.write_text(
        json.dumps(
            {
                "report_date": report_date,
                "generated_at": (
                    f"{report_date}T15:40:00+09:00"
                ),
                "status": "complete",
                "summary": {
                    "trade_count": 2,
                    "net_profit_loss": net_profit_loss,
                },
                "strategy_breakdown": [],
                "symbol_breakdown": [],
                "error_count": 0,
                "recovery_count": 0,
                "notes": [],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_reader_returns_unavailable_when_empty(
    tmp_path: Path,
) -> None:
    payload = DailyReportReader(
        tmp_path / "daily"
    ).read_latest()

    assert not payload["available"]
    assert payload["status"] == "not_available"


def test_reader_selects_latest_iso_date(
    tmp_path: Path,
) -> None:
    directory = tmp_path / "daily"
    write_report(
        directory,
        "2026-08-01",
        net_profit_loss=100.0,
    )
    write_report(
        directory,
        "2026-08-03",
        net_profit_loss=300.0,
    )
    (
        directory / "summary.json"
    ).write_text(
        "{}",
        encoding="utf-8",
    )

    payload = DailyReportReader(
        directory
    ).read_latest()

    assert payload["available"]
    assert payload["report_date"] == "2026-08-03"
    assert (
        payload["summary"]["net_profit_loss"]
        == 300.0
    )


def test_reader_loads_requested_date(
    tmp_path: Path,
) -> None:
    directory = tmp_path / "daily"
    write_report(
        directory,
        "2026-08-02",
        net_profit_loss=-200.0,
    )

    payload = DailyReportReader(
        directory
    ).read_for_date(
        date(2026, 8, 2)
    )

    assert payload["available"]
    assert payload["report_date"] == "2026-08-02"


def test_reader_rejects_invalid_json(
    tmp_path: Path,
) -> None:
    directory = tmp_path / "daily"
    directory.mkdir()
    (
        directory / "2026-08-01.json"
    ).write_text(
        "{broken",
        encoding="utf-8",
    )

    with pytest.raises(
        DailyReportReadError,
    ):
        DailyReportReader(
            directory
        ).read_latest()
