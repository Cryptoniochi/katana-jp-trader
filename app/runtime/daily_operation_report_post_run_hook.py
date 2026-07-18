"""Daily Operation ReportをPaperTradingDay Post-run Hookへ接続する。"""

from __future__ import annotations

from typing import Protocol

from app.runtime.paper_trading_day_models import (
    PaperTradingDayResult,
)


class DailyOperationReportPublisher(Protocol):
    """日次運用レポート公開処理。"""

    def publish(
        self,
        result: PaperTradingDayResult,
    ):
        """日次JSON・HTMLレポートを生成する。"""


class DailyOperationReportPostRunHook:
    """Paper Trading終了後に日次レポートを生成する。"""

    def __init__(
        self,
        *,
        report_publisher: DailyOperationReportPublisher,
    ) -> None:
        """Report Publisherを設定する。"""

        self.report_publisher = report_publisher

    def handle(
        self,
        result: PaperTradingDayResult,
    ) -> None:
        """日次運用結果からレポートを生成する。"""

        self.report_publisher.publish(result)
