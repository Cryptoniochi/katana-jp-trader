"""完結トレードからバックテスト指標を算出する。"""

from app.backtest.performance_metrics_models import (
    BacktestPerformanceMetrics,
)
from app.backtest.trade_report_models import (
    BacktestTradeReport,
)


class BacktestPerformanceMetricsService:
    """TradeReportを主要成績指標へ変換する。"""

    def create_metrics(
        self,
        report: BacktestTradeReport,
    ) -> BacktestPerformanceMetrics:
        """完結トレード一覧から成績指標を算出する。"""

        profits = [
            trade.net_profit_loss
            for trade in report.trades
            if trade.is_winner
        ]
        losses = [
            abs(trade.net_profit_loss)
            for trade in report.trades
            if trade.is_loser
        ]

        gross_profit = sum(profits)
        gross_loss = sum(losses)
        net_profit_loss = sum(
            trade.net_profit_loss
            for trade in report.trades
        )

        win_rate = (
            None
            if report.trade_count == 0
            else report.winning_trade_count
            / report.trade_count
        )

        profit_factor = (
            None
            if gross_loss == 0
            else gross_profit / gross_loss
        )

        average_profit = (
            None
            if not profits
            else gross_profit / len(profits)
        )

        average_loss = (
            None
            if not losses
            else gross_loss / len(losses)
        )

        expectancy = (
            None
            if report.trade_count == 0
            else net_profit_loss / report.trade_count
        )

        (
            maximum_consecutive_wins,
            maximum_consecutive_losses,
        ) = self._calculate_streaks(report)

        return BacktestPerformanceMetrics(
            trade_count=report.trade_count,
            winning_trade_count=(
                report.winning_trade_count
            ),
            losing_trade_count=(
                report.losing_trade_count
            ),
            flat_trade_count=(
                report.flat_trade_count
            ),
            gross_profit=gross_profit,
            gross_loss=gross_loss,
            net_profit_loss=net_profit_loss,
            win_rate=win_rate,
            profit_factor=profit_factor,
            average_profit=average_profit,
            average_loss=average_loss,
            expectancy=expectancy,
            maximum_consecutive_wins=(
                maximum_consecutive_wins
            ),
            maximum_consecutive_losses=(
                maximum_consecutive_losses
            ),
            unmatched_buy_quantity=(
                report.unmatched_buy_quantity
            ),
            unmatched_sell_quantity=(
                report.unmatched_sell_quantity
            ),
        )

    @staticmethod
    def _calculate_streaks(
        report: BacktestTradeReport,
    ) -> tuple[int, int]:
        """最大連勝数と最大連敗数を返す。"""

        current_wins = 0
        current_losses = 0
        maximum_wins = 0
        maximum_losses = 0

        for trade in report.trades:
            if trade.is_winner:
                current_wins += 1
                current_losses = 0
                maximum_wins = max(
                    maximum_wins,
                    current_wins,
                )
                continue

            if trade.is_loser:
                current_losses += 1
                current_wins = 0
                maximum_losses = max(
                    maximum_losses,
                    current_losses,
                )
                continue

            current_wins = 0
            current_losses = 0

        return maximum_wins, maximum_losses
