"""日次取引レポートモデルのテスト。"""

from datetime import date, datetime, timezone

import pytest

from app.runtime.daily_report_models import (
    DailyReportBreakdownRow,
    DailyReportStatus,
    DailyReportSummary,
    DailyTradingReport,
)


NOW = datetime(
    2026,
    8,
    3,
    15,
    40,
    tzinfo=timezone.utc,
)


def create_summary() -> DailyReportSummary:
    return DailyReportSummary(
        trade_count=4,
        win_count=2,
        loss_count=1,
        flat_count=1,
        gross_profit=10000.0,
        gross_loss=-3000.0,
        net_profit_loss=7000.0,
        win_rate=0.5,
        profit_factor=10_000.0 / 3_000.0,
        average_win=5000.0,
        average_loss=-3000.0,
        maximum_drawdown=-2500.0,
    )


def test_report_serializes_to_json_compatible_dict() -> None:
    report = DailyTradingReport(
        report_date=date(2026, 8, 3),
        generated_at=NOW,
        status=DailyReportStatus.COMPLETE,
        summary=create_summary(),
        strategy_breakdown=(
            DailyReportBreakdownRow(
                key="orb",
                label="ORB",
                trade_count=2,
                net_profit_loss=5000.0,
                win_rate=0.5,
                profit_factor=2.0,
            ),
        ),
        error_count=0,
        recovery_count=1,
    )

    payload = report.to_dict()

    assert payload["report_date"] == "2026-08-03"
    assert payload["status"] == "complete"
    assert payload["summary"]["trade_count"] == 4
    assert payload["strategy_breakdown"][0][
        "key"
    ] == "orb"
    assert payload["recovery_count"] == 1


def test_summary_rejects_mismatched_trade_count() -> None:
    with pytest.raises(
        ValueError,
        match="取引件数",
    ):
        DailyReportSummary(
            trade_count=3,
            win_count=1,
            loss_count=1,
            flat_count=0,
            gross_profit=100.0,
            gross_loss=-50.0,
            net_profit_loss=50.0,
            win_rate=0.5,
            profit_factor=2.0,
            average_win=100.0,
            average_loss=-50.0,
            maximum_drawdown=-50.0,
        )


def test_empty_report_requires_zero_trades() -> None:
    with pytest.raises(
        ValueError,
        match="EMPTY",
    ):
        DailyTradingReport(
            report_date=date(2026, 8, 3),
            generated_at=NOW,
            status=DailyReportStatus.EMPTY,
            summary=create_summary(),
        )


def test_complete_report_rejects_notes() -> None:
    with pytest.raises(
        ValueError,
        match="COMPLETE",
    ):
        DailyTradingReport(
            report_date=date(2026, 8, 3),
            generated_at=NOW,
            status=DailyReportStatus.COMPLETE,
            summary=create_summary(),
            notes=("missing source",),
        )


def test_partial_report_accepts_notes() -> None:
    report = DailyTradingReport(
        report_date=date(2026, 8, 3),
        generated_at=NOW,
        status=DailyReportStatus.PARTIAL,
        summary=create_summary(),
        notes=("Recovery log was unavailable.",),
    )

    assert report.notes == (
        "Recovery log was unavailable.",
    )
