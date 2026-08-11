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


def test_post_run_hook_writes_date_scoped_history(
    tmp_path: Path,
) -> None:
    report = tmp_path / "latest.json"
    history = tmp_path / "history"
    auditor = FakeAuditService()
    hook = WatchlistExecutionIntegrityPostRunHook(
        audit_service=auditor,
        report_path=report,
        history_directory=history,
    )

    hook.handle(
        SimpleNamespace(trading_date=DAY)
    )

    archived = history / "2026-08-12.json"
    assert archived.exists()
    payload = json.loads(
        archived.read_text(encoding="utf-8")
    )
    assert payload["trading_date"] == "2026-08-12"
    assert payload["integrity_ok"] is True


def test_later_latest_report_does_not_overwrite_history(
    tmp_path: Path,
) -> None:
    report = tmp_path / "latest.json"
    history = tmp_path / "history"

    first = FakeAuditService()
    hook = WatchlistExecutionIntegrityPostRunHook(
        audit_service=first,
        report_path=report,
        history_directory=history,
    )
    hook.handle(
        SimpleNamespace(trading_date=DAY)
    )

    later_day = date(2026, 8, 13)

    class LaterAuditService:
        def audit(self, *, trading_date: date):
            assert trading_date == later_day

            class LaterResult:
                def to_dict(self):
                    return {
                        "trading_date": later_day.isoformat(),
                        "integrity_ok": False,
                    }

            return LaterResult()

    WatchlistExecutionIntegrityPostRunHook(
        audit_service=LaterAuditService(),
        report_path=report,
        history_directory=history,
    ).handle(
        SimpleNamespace(trading_date=later_day)
    )

    archived = json.loads(
        (history / "2026-08-12.json").read_text(
            encoding="utf-8"
        )
    )
    latest = json.loads(
        report.read_text(encoding="utf-8")
    )

    assert archived["trading_date"] == "2026-08-12"
    assert archived["integrity_ok"] is True
    assert latest["trading_date"] == "2026-08-13"
    assert latest["integrity_ok"] is False
