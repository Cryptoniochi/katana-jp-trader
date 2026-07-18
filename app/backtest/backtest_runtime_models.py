"""既存Event-driven Backtestを運用単位で扱うモデル。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.backtest.event_driven_backtest_runner import (
    EventDrivenBacktestRunResult,
)
from app.backtest.performance_metrics_models import (
    BacktestPerformanceMetrics,
)
from app.backtest.trade_report_models import (
    BacktestTradeReport,
)


class BacktestRuntimeStatus(StrEnum):
    """Backtest Runtimeの終了状態。"""

    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class BacktestRuntimeResult:
    """1回のBacktest実行・分析結果。"""

    started_at: datetime
    completed_at: datetime
    status: BacktestRuntimeStatus
    run_result: EventDrivenBacktestRunResult | None
    trade_report: BacktestTradeReport | None
    metrics: BacktestPerformanceMetrics | None
    error_message: str | None = None

    def __post_init__(self) -> None:
        """日時・状態・結果の整合性を検証する。"""

        for name, value in {
            "開始日時": self.started_at,
            "完了日時": self.completed_at,
        }.items():
            if value.tzinfo is None:
                raise ValueError(
                    f"{name}にはタイムゾーンが必要です。"
                )

        if self.completed_at < self.started_at:
            raise ValueError(
                "完了日時は開始日時以後である必要があります。"
            )

        error_message = (
            None
            if self.error_message is None
            else self.error_message.strip() or None
        )

        if self.status is BacktestRuntimeStatus.COMPLETED:
            if (
                self.run_result is None
                or self.trade_report is None
                or self.metrics is None
            ):
                raise ValueError(
                    "完了結果には実行結果・取引レポート・"
                    "成績指標が必要です。"
                )

            if error_message is not None:
                raise ValueError(
                    "完了結果にはエラーメッセージを設定できません。"
                )

        if self.status is BacktestRuntimeStatus.FAILED:
            if error_message is None:
                raise ValueError(
                    "失敗結果にはエラーメッセージが必要です。"
                )

        object.__setattr__(
            self,
            "error_message",
            error_message,
        )

    @property
    def elapsed_seconds(self) -> float:
        """Backtest実行時間を秒で返す。"""

        return (
            self.completed_at - self.started_at
        ).total_seconds()

    @property
    def frame_count(self) -> int:
        """再生Frame数を返す。"""

        if self.run_result is None:
            return 0

        return self.run_result.frame_count

    @property
    def signal_count(self) -> int:
        """生成Signal数を返す。"""

        if self.run_result is None:
            return 0

        return self.run_result.signal_count

    @property
    def order_count(self) -> int:
        """Queue登録注文数を返す。"""

        if self.run_result is None:
            return 0

        return self.run_result.queued_count

    @property
    def execution_count(self) -> int:
        """保存約定数を返す。"""

        if self.run_result is None:
            return 0

        return self.run_result.execution_count

    @property
    def is_successful(self) -> bool:
        """Backtestが正常完了したか返す。"""

        return self.status is BacktestRuntimeStatus.COMPLETED
