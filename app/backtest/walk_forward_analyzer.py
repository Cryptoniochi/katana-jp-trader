"""Walk-Forward Optimization結果を集計する。"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable

from app.backtest.performance_metrics_models import (
    BacktestPerformanceMetrics,
)
from app.backtest.walk_forward_result_models import (
    WalkForwardResult,
)
from app.backtest.walk_forward_summary_models import (
    WalkForwardParameterFrequency,
    WalkForwardPerformanceAggregate,
    WalkForwardSummary,
)
from app.trading.equity_curve_models import (
    EquityCurveReport,
)


class WalkForwardAnalyzer:
    """学習成績とOOS検証成績をウィンドウ横断で集計する。"""

    def create_summary(
        self,
        result: WalkForwardResult,
    ) -> WalkForwardSummary:
        """Walk-Forward結果全体のサマリーを作成する。"""

        completed = result.completed_results

        training_items = tuple(
            (
                item.best_training_run.metrics,
                item.best_training_run.equity_curve_report,
            )
            for item in completed
            if (
                item.best_training_run is not None
                and item.best_training_run.metrics is not None
            )
        )
        validation_items = tuple(
            (
                item.validation_result.metrics,
                item.validation_result.equity_curve_report,
            )
            for item in completed
            if item.validation_result is not None
        )

        profitable_validation_count = sum(
            metrics.net_profit_loss > 0
            for metrics, _report in validation_items
        )
        profitable_validation_rate = (
            None
            if not validation_items
            else (
                profitable_validation_count
                / len(validation_items)
            )
        )

        selected_counts = Counter(
            item.selected_parameter.parameter_id
            for item in completed
            if item.selected_parameter is not None
        )
        parameter_frequencies = tuple(
            WalkForwardParameterFrequency(
                parameter_id=parameter_id,
                selected_count=count,
            )
            for parameter_id, count in sorted(
                selected_counts.items(),
                key=lambda pair: (
                    -pair[1],
                    pair[0],
                ),
            )
        )

        return WalkForwardSummary(
            window_count=result.window_count,
            completed_window_count=result.completed_count,
            failed_window_count=result.failed_count,
            profitable_validation_window_count=(
                profitable_validation_count
            ),
            validation_profitable_window_rate=(
                profitable_validation_rate
            ),
            training=self._aggregate(training_items),
            validation=self._aggregate(validation_items),
            parameter_frequencies=parameter_frequencies,
        )

    @staticmethod
    def _aggregate(
        items: Iterable[
            tuple[
                BacktestPerformanceMetrics,
                EquityCurveReport | None,
            ]
        ],
    ) -> WalkForwardPerformanceAggregate:
        """成績指標と資産曲線を合算する。"""

        materialized = tuple(items)
        metrics_items = tuple(
            metrics
            for metrics, _report in materialized
        )

        trade_count = sum(
            metrics.trade_count
            for metrics in metrics_items
        )
        winning_trade_count = sum(
            metrics.winning_trade_count
            for metrics in metrics_items
        )
        losing_trade_count = sum(
            metrics.losing_trade_count
            for metrics in metrics_items
        )
        flat_trade_count = sum(
            metrics.flat_trade_count
            for metrics in metrics_items
        )
        gross_profit = sum(
            metrics.gross_profit
            for metrics in metrics_items
        )
        gross_loss = sum(
            metrics.gross_loss
            for metrics in metrics_items
        )
        net_profit_loss = sum(
            metrics.net_profit_loss
            for metrics in metrics_items
        )

        win_rate = (
            None
            if trade_count == 0
            else winning_trade_count / trade_count
        )
        profit_factor = (
            None
            if gross_loss == 0
            else gross_profit / gross_loss
        )
        expectancy = (
            None
            if trade_count == 0
            else net_profit_loss / trade_count
        )
        average_net_profit_loss = (
            None
            if not metrics_items
            else net_profit_loss / len(metrics_items)
        )

        drawdowns = tuple(
            report.maximum_drawdown
            for _metrics, report in materialized
            if report is not None
        )
        maximum_drawdown = (
            None
            if not drawdowns
            else max(drawdowns)
        )

        return WalkForwardPerformanceAggregate(
            result_count=len(metrics_items),
            trade_count=trade_count,
            winning_trade_count=winning_trade_count,
            losing_trade_count=losing_trade_count,
            flat_trade_count=flat_trade_count,
            gross_profit=gross_profit,
            gross_loss=gross_loss,
            net_profit_loss=net_profit_loss,
            win_rate=win_rate,
            profit_factor=profit_factor,
            expectancy=expectancy,
            average_net_profit_loss=average_net_profit_loss,
            maximum_drawdown=maximum_drawdown,
        )
