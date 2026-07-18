"""既存EventDrivenBacktestRunnerを再利用するRuntime Facade。"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Protocol

from app.backtest.event_driven_backtest_runner import (
    EventDrivenBacktestRunResult,
)
from app.backtest.performance_metrics_models import (
    BacktestPerformanceMetrics,
)
from app.backtest.backtest_runtime_models import (
    BacktestRuntimeResult,
    BacktestRuntimeStatus,
)
from app.backtest.trade_report_models import (
    BacktestTradeReport,
)
from app.trading.order_models import OrderType


class BacktestRuntimeExecutor(Protocol):
    """既存Event-driven Backtest実行処理。"""

    def run(
        self,
        *,
        order_type: OrderType = OrderType.MARKET,
        equity_curve_limit: int = 10_000,
        continue_on_error: bool = False,
    ) -> EventDrivenBacktestRunResult:
        """保存済みHistorical Barを再生する。"""


class BacktestRuntimeAnalyzer(Protocol):
    """Backtest実行後の取引レポート・成績指標作成処理。"""

    def create(
        self,
        run_result: EventDrivenBacktestRunResult,
    ) -> tuple[
        BacktestTradeReport,
        BacktestPerformanceMetrics,
    ]:
        """実行結果から取引レポートと成績指標を作成する。"""


class BacktestRuntime:
    """既存Backtest Pipelineを1回の運用単位として実行する。"""

    def __init__(
        self,
        *,
        executor: BacktestRuntimeExecutor,
        analyzer: BacktestRuntimeAnalyzer,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        """Executor・Analyzer・時計を設定する。"""

        self.executor = executor
        self.analyzer = analyzer
        self.now_provider = (
            now_provider
            if now_provider is not None
            else lambda: datetime.now(timezone.utc)
        )

    def run(
        self,
        *,
        order_type: OrderType = OrderType.MARKET,
        equity_curve_limit: int = 10_000,
        continue_on_error: bool = False,
    ) -> BacktestRuntimeResult:
        """Backtest実行と分析を一体で行う。"""

        if equity_curve_limit <= 0:
            raise ValueError(
                "資産曲線取得件数は0より大きい必要があります。"
            )

        started_at = self._current_time()

        try:
            run_result = self.executor.run(
                order_type=order_type,
                equity_curve_limit=equity_curve_limit,
                continue_on_error=continue_on_error,
            )
            trade_report, metrics = self.analyzer.create(
                run_result
            )

            return BacktestRuntimeResult(
                started_at=started_at,
                completed_at=self._current_time(),
                status=BacktestRuntimeStatus.COMPLETED,
                run_result=run_result,
                trade_report=trade_report,
                metrics=metrics,
            )

        except Exception as error:
            if not continue_on_error:
                raise

            return BacktestRuntimeResult(
                started_at=started_at,
                completed_at=self._current_time(),
                status=BacktestRuntimeStatus.FAILED,
                run_result=None,
                trade_report=None,
                metrics=None,
                error_message=(
                    str(error).strip()
                    or type(error).__name__
                ),
            )

    def _current_time(self) -> datetime:
        """UTCへ正規化した現在日時を返す。"""

        current = self.now_provider()

        if current.tzinfo is None:
            raise ValueError(
                "現在日時にはタイムゾーンが必要です。"
            )

        return current.astimezone(timezone.utc)
