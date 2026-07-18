"""DailyOperationReportServiceのテスト。"""

import json
from datetime import datetime, timezone

from app.runtime.daily_operation_report_service import (
    DailyOperationReportService,
)
from app.runtime.paper_trading_daily_repository import (
    PaperTradingDailyRecord,
)
from app.runtime.paper_trading_day_models import (
    PaperTradingDayResult,
    PaperTradingDayStopReason,
)
from app.runtime.paper_trading_runtime_models import (
    PaperTradingDailySummary,
    PaperTradingRuntimeStatus,
)


NOW = datetime(
    2026,
    7,
    18,
    0,
    0,
    tzinfo=timezone.utc,
)


def create_result() -> PaperTradingDayResult:
    summary = PaperTradingDailySummary(
        trading_date=NOW.date(),
        started_at=NOW,
        completed_at=NOW,
        status=PaperTradingRuntimeStatus.COMPLETED,
        records=(),
        initial_equity=1_000_000.0,
        final_equity=1_010_000.0,
    )
    record = PaperTradingDailyRecord(
        trading_date=NOW.date(),
        status=PaperTradingRuntimeStatus.COMPLETED,
        started_at=NOW,
        completed_at=NOW,
        cycle_count=0,
        successful_cycle_count=0,
        failed_cycle_count=0,
        signal_count=0,
        execution_count=0,
        initial_equity=1_000_000.0,
        final_equity=1_010_000.0,
        net_profit_loss=10_000.0,
        return_rate=0.01,
        error_message=None,
        payload={},
        created_at=NOW,
        updated_at=NOW,
    )

    return PaperTradingDayResult(
        trading_date=NOW.date(),
        started_at=NOW,
        completed_at=NOW,
        stop_reason=PaperTradingDayStopReason.MARKET_CLOSED,
        summary=summary,
        record=record,
        dashboard_published=True,
    )


def test_service_generates_json_and_html(tmp_path) -> None:
    service = DailyOperationReportService(
        report_root=tmp_path / "reports",
        now_provider=lambda: NOW,
    )

    result = service.generate(create_result())

    assert result.paths.json_path.exists()
    assert result.paths.html_path.exists()
    assert result.json_size_bytes > 0
    assert result.html_size_bytes > 0

    payload = json.loads(
        result.paths.json_path.read_text(
            encoding="utf-8"
        )
    )
    html = result.paths.html_path.read_text(
        encoding="utf-8"
    )

    assert payload["trading_date"] == "2026-07-18"
    assert payload["net_profit_loss"] == 10_000.0
    assert payload["report_generated_at"] == NOW.isoformat()
    assert "Daily Operations Report" in html
    assert "¥10,000" in html
    assert not (
        result.paths.directory
        / "summary.json.tmp"
    ).exists()
    assert not (
        result.paths.directory
        / "summary.html.tmp"
    ).exists()


def test_service_overwrites_existing_report(tmp_path) -> None:
    service = DailyOperationReportService(
        report_root=tmp_path / "reports",
        now_provider=lambda: NOW,
    )
    operation_result = create_result()

    first = service.generate(operation_result)
    first.paths.html_path.write_text(
        "broken",
        encoding="utf-8",
    )
    second = service.generate(operation_result)

    assert "broken" not in (
        second.paths.html_path.read_text(
            encoding="utf-8"
        )
    )
