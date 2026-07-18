"""TradingOperationResult JSON変換のテスト。"""

from datetime import datetime, timezone
from pathlib import Path

from app.runtime.daily_operation_report_models import (
    DailyOperationReportPaths,
    DailyOperationReportResult,
)
from app.runtime.daily_operation_report_publish_service import (
    DailyOperationReportPublishResult,
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
from app.runtime.trading_operation_orchestrator import (
    TradingOperationResult,
)
from app.runtime.trading_operation_report import (
    trading_operation_result_to_dict,
)


NOW = datetime(
    2026,
    7,
    18,
    0,
    0,
    tzinfo=timezone.utc,
)


def test_operation_result_is_json_compatible() -> None:
    """運用・レポート・Hook結果を辞書化できる。"""

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
    operation = PaperTradingDayResult(
        trading_date=NOW.date(),
        started_at=NOW,
        completed_at=NOW,
        stop_reason=PaperTradingDayStopReason.MARKET_CLOSED,
        summary=summary,
        record=record,
        dashboard_published=True,
    )
    directory = Path(
        "reports/daily/2026-07-18"
    )
    report = DailyOperationReportPublishResult(
        report_result=DailyOperationReportResult(
            trading_date=NOW.date(),
            generated_at=NOW,
            paths=DailyOperationReportPaths(
                trading_date=NOW.date(),
                directory=directory,
                json_path=directory / "summary.json",
                html_path=directory / "summary.html",
            ),
            json_size_bytes=100,
            html_size_bytes=200,
        )
    )
    result = TradingOperationResult(
        operation_result=operation,
        report_result=report,
        report_error_message=None,
        completed_hook_count=1,
        hook_error_messages=("alert failed",),
    )

    payload = trading_operation_result_to_dict(result)

    assert payload["trading_date"] == "2026-07-18"
    assert payload["report"]["published"] is True
    assert payload["report"]["html_path"].endswith(
        "summary.html"
    )
    assert payload["hooks"]["completed_count"] == 1
    assert payload["hooks"]["failure_count"] == 1
