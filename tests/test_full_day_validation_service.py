"""FullDayValidationService tests。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from app.runtime.full_day_validation_service import (
    FullDayValidationService,
)


DAY = date(2026, 8, 12)
NOW = datetime(
    2026,
    8,
    12,
    6,
    45,
    tzinfo=timezone.utc,
)


@dataclass
class FakeDailyRecord:
    status: object
    cycle_count: int = 660
    successful_cycle_count: int = 660
    failed_cycle_count: int = 0
    signal_count: int = 2
    execution_count: int = 4
    net_profit_loss: float = 5000.0
    error_message: str | None = None


class FakeRepository:
    def __init__(
        self,
        record: FakeDailyRecord | None,
    ) -> None:
        self.record = record

    def get(
        self,
        trading_date: date,
    ):
        assert trading_date == DAY
        return self.record


def _write(
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


def _service(
    tmp_path: Path,
    *,
    record: FakeDailyRecord | None = None,
) -> FullDayValidationService:
    runtime = tmp_path / "runtime.json"
    integrity = tmp_path / "integrity.json"
    reports = tmp_path / "daily"

    _write(
        runtime,
        {
            "trading_date": DAY.isoformat(),
            "state": "completed",
            "cycle_count": 660,
            "successful_cycle_count": 660,
            "failed_cycle_count": 0,
            "signal_count": 2,
            "execution_count": 4,
            "cycle_execution_count": 2,
            "external_execution_count": 2,
            "open_position_count": 0,
            "portfolio_position_count": 0,
            "realized_profit_loss": 5000.0,
            "session_equity_change": 5000.0,
            "pnl_reconciliation_difference": 0.0,
            "pnl_consistent": True,
            "risk_evaluated_cycle_count": 2,
            "risk_blocked_cycle_count": 0,
            "error_message": None,
        },
    )
    _write(
        integrity,
        {
            "trading_date": DAY.isoformat(),
            "integrity_ok": True,
            "trace_available": True,
            "selected_count": 3,
            "loaded_count": 3,
            "monitored_count": 3,
            "signal_count": 2,
            "execution_count": 4,
            "selected_not_loaded_codes": [],
            "loaded_not_monitored_codes": [],
            "monitored_not_loaded_codes": [],
            "orphan_signal_codes": [],
            "orphan_execution_codes": [],
        },
    )
    _write(
        reports / f"{DAY.isoformat()}.json",
        {
            "report_date": DAY.isoformat(),
            "status": "complete",
            "summary": {
                "trade_count": 2,
                "net_profit_loss": 5000.0,
            },
            "error_count": 0,
            "recovery_count": 0,
        },
    )

    return FullDayValidationService(
        database_path=tmp_path / "katana.db",
        runtime_status_path=runtime,
        integrity_report_path=integrity,
        daily_report_directory=reports,
        daily_repository=FakeRepository(
            record
            or FakeDailyRecord(
                status=SimpleNamespace(
                    value="completed"
                )
            )
        ),
        now_provider=lambda: NOW,
    )


def test_full_day_validation_passes_consistent_day(
    tmp_path: Path,
) -> None:
    result = _service(tmp_path).validate(
        trading_date=DAY
    )

    assert result.passed is True
    assert result.failed_check_count == 0


def test_full_day_validation_fails_open_positions(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    payload = json.loads(
        service.runtime_status_path.read_text(
            encoding="utf-8"
        )
    )
    payload["open_position_count"] = 1
    _write(
        service.runtime_status_path,
        payload,
    )

    result = service.validate(
        trading_date=DAY
    )

    assert result.passed is False
    failed = {
        check.key
        for check in result.checks
        if not check.passed
    }
    assert "end_of_day_positions" in failed


def test_full_day_validation_fails_integrity_mismatch(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    payload = json.loads(
        service.integrity_report_path.read_text(
            encoding="utf-8"
        )
    )
    payload["integrity_ok"] = False
    _write(
        service.integrity_report_path,
        payload,
    )

    result = service.validate(
        trading_date=DAY
    )

    assert result.passed is False
    assert any(
        check.key
        == "watchlist_execution_integrity"
        and not check.passed
        for check in result.checks
    )


def test_full_day_validation_fails_pnl_mismatch(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    report_path = (
        service.daily_report_directory
        / f"{DAY.isoformat()}.json"
    )
    payload = json.loads(
        report_path.read_text(encoding="utf-8")
    )
    payload["summary"]["net_profit_loss"] = 4900.0
    _write(report_path, payload)

    result = service.validate(
        trading_date=DAY
    )

    assert result.passed is False
    assert any(
        check.key == "pnl_source_reconciliation"
        and not check.passed
        for check in result.checks
    )


def test_empty_no_trade_day_can_validate(
    tmp_path: Path,
) -> None:
    service = _service(
        tmp_path,
        record=FakeDailyRecord(
            status=SimpleNamespace(
                value="completed"
            ),
            signal_count=0,
            execution_count=0,
            net_profit_loss=0.0,
        ),
    )

    runtime = json.loads(
        service.runtime_status_path.read_text(
            encoding="utf-8"
        )
    )
    runtime["signal_count"] = 0
    runtime["execution_count"] = 0
    runtime["realized_profit_loss"] = 0.0
    runtime["session_equity_change"] = 0.0
    _write(
        service.runtime_status_path,
        runtime,
    )

    integrity = json.loads(
        service.integrity_report_path.read_text(
            encoding="utf-8"
        )
    )
    integrity["signal_count"] = 0
    integrity["execution_count"] = 0
    _write(
        service.integrity_report_path,
        integrity,
    )

    report_path = (
        service.daily_report_directory
        / f"{DAY.isoformat()}.json"
    )
    report = json.loads(
        report_path.read_text(encoding="utf-8")
    )
    report["status"] = "empty"
    report["summary"]["trade_count"] = 0
    report["summary"]["net_profit_loss"] = 0.0
    _write(report_path, report)

    result = service.validate(
        trading_date=DAY
    )

    assert result.passed is True


def test_stale_integrity_is_not_reported_as_pass(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    payload = json.loads(
        service.integrity_report_path.read_text(
            encoding="utf-8"
        )
    )
    payload["trading_date"] = "2026-08-11"
    payload["integrity_ok"] = True
    _write(
        service.integrity_report_path,
        payload,
    )

    result = service.validate(
        trading_date=DAY
    )

    integrity_check = next(
        check
        for check in result.checks
        if check.key
        == "watchlist_execution_integrity"
    )
    assert integrity_check.passed is False
    assert "stale" in integrity_check.message.lower()
