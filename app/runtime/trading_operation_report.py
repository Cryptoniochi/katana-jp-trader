"""TradingOperationResultをJSON互換辞書へ変換する。"""

from __future__ import annotations

from typing import Any

from app.runtime.paper_trading_day_report import (
    paper_trading_day_result_to_dict,
)
from app.runtime.trading_operation_orchestrator import (
    TradingOperationResult,
)


def trading_operation_result_to_dict(
    result: TradingOperationResult,
) -> dict[str, Any]:
    """運用・レポート・Hook結果を辞書へ変換する。"""

    report = result.report_result
    report_result = (
        report.report_result
        if report is not None
        else None
    )

    return {
        "trading_date": result.trading_date.isoformat(),
        "operation": paper_trading_day_result_to_dict(
            result.operation_result
        ),
        "report": {
            "published": result.report_published,
            "error_message": (
                result.report_error_message
            ),
            "json_path": (
                str(report_result.paths.json_path)
                if report_result is not None
                else None
            ),
            "html_path": (
                str(report_result.paths.html_path)
                if report_result is not None
                else None
            ),
        },
        "hooks": {
            "completed_count": (
                result.completed_hook_count
            ),
            "failure_count": (
                result.hook_failure_count
            ),
            "error_messages": list(
                result.hook_error_messages
            ),
        },
    }
