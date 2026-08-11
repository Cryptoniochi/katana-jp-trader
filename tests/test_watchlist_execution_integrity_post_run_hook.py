"""WatchlistExecutionIntegrityPostRunHook tests."""

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from app.runtime.watchlist_execution_integrity_post_run_hook import (
    WatchlistExecutionIntegrityPostRunHook,
)


DAY = date(2026, 8, 12)


@dataclass
class FakeAuditResult:
    integrity_ok: bool = True

    def to_dict(self) -> dict[str, object]:
        return {
            "trading_date": DAY.isoformat(),
            "integrity_ok": self.integrity_ok,
        }


class FakeAuditService:
    def __init__(
        self,
        *,
        result: FakeAuditResult | None = None,
        error: Exception | None = None,
    ) -> None:
        self.result = result or FakeAuditResult()
        self.error = error
        self.called_dates: list[date] = []

    def audit(
        self,
        *,
        trading_date: date,
    ) -> FakeAuditResult:
        self.called_dates.append(trading_date)
        if self.error is not None:
            raise self.error
        return self.result


def test_post_run_hook_audits_result_trading_date_and_writes_report(
    tmp_path: Path,
) -> None:
    report = tmp_path / "service" / "integrity.json"
    auditor = FakeAuditService()
    hook = WatchlistExecutionIntegrityPostRunHook(
        audit_service=auditor,
        report_path=report,
    )

    hook.handle(
        SimpleNamespace(trading_date=DAY)
    )

    assert auditor.called_dates == [DAY]
    payload = json.loads(
        report.read_text(encoding="utf-8")
    )
    assert payload["trading_date"] == "2026-08-12"
    assert payload["integrity_ok"] is True
    assert not report.with_suffix(".json.tmp").exists()


def test_post_run_hook_persists_failed_integrity_result(
    tmp_path: Path,
) -> None:
    report = tmp_path / "integrity.json"
    auditor = FakeAuditService(
        result=FakeAuditResult(integrity_ok=False)
    )
    hook = WatchlistExecutionIntegrityPostRunHook(
        audit_service=auditor,
        report_path=report,
    )

    hook.handle(
        SimpleNamespace(trading_date=DAY)
    )

    payload = json.loads(
        report.read_text(encoding="utf-8")
    )
    assert payload["integrity_ok"] is False


def test_post_run_hook_propagates_audit_errors(
    tmp_path: Path,
) -> None:
    report = tmp_path / "integrity.json"
    auditor = FakeAuditService(
        error=RuntimeError("audit failed")
    )
    hook = WatchlistExecutionIntegrityPostRunHook(
        audit_service=auditor,
        report_path=report,
    )

    try:
        hook.handle(
            SimpleNamespace(trading_date=DAY)
        )
    except RuntimeError as error:
        assert str(error) == "audit failed"
    else:
        raise AssertionError("RuntimeError was not raised")

    assert not report.exists()
