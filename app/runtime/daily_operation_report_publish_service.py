"""日次運用結果のレポート生成を任意Hookとして提供する。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.runtime.daily_operation_report_models import (
    DailyOperationReportResult,
)
from app.runtime.paper_trading_day_models import (
    PaperTradingDayResult,
)


class DailyOperationReportGenerator(Protocol):
    """日次運用レポート生成処理。"""

    def generate(
        self,
        result: PaperTradingDayResult,
    ) -> DailyOperationReportResult:
        """日次レポートを生成する。"""


@dataclass(frozen=True, slots=True)
class DailyOperationReportPublishResult:
    """日次レポート公開結果。"""

    report_result: DailyOperationReportResult


class DailyOperationReportPublishService:
    """Paper Trading日次結果からレポートを公開する。"""

    def __init__(
        self,
        *,
        report_generator: DailyOperationReportGenerator,
    ) -> None:
        """Report Generatorを設定する。"""

        self.report_generator = report_generator

    def publish(
        self,
        result: PaperTradingDayResult,
    ) -> DailyOperationReportPublishResult:
        """JSON・HTML日次レポートを生成する。"""

        report_result = self.report_generator.generate(
            result
        )

        return DailyOperationReportPublishResult(
            report_result=report_result
        )
