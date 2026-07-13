"""取引一覧を集計するバックテストエンジン。"""

from app.backtest.result import BacktestResult
from app.backtest.trade import Trade


class BacktestEngine:
    """取引一覧から損益・勝敗・リスク指標を計算する。"""

    def run(self, trades: list[Trade]) -> BacktestResult:
        """取引一覧を集計してバックテスト結果を返す。"""

        profits = [trade.profit for trade in trades]

        total_profit = sum(profits)
        gross_profit = sum(profit for profit in profits if profit > 0)
        gross_loss = sum(profit for profit in profits if profit < 0)

        win_count = sum(1 for profit in profits if profit > 0)
        loss_count = sum(1 for profit in profits if profit < 0)
        breakeven_count = sum(1 for profit in profits if profit == 0)

        max_drawdown = self._calculate_max_drawdown(profits)

        return BacktestResult(
            total_profit=total_profit,
            gross_profit=gross_profit,
            gross_loss=gross_loss,
            max_drawdown=max_drawdown,
            trade_count=len(trades),
            win_count=win_count,
            loss_count=loss_count,
            breakeven_count=breakeven_count,
        )

    @staticmethod
    def _calculate_max_drawdown(profits: list[float]) -> float:
        """累積損益から最大ドローダウンを金額で計算する。"""

        cumulative_profit = 0.0
        peak = 0.0
        max_drawdown = 0.0

        for profit in profits:
            cumulative_profit += profit
            peak = max(peak, cumulative_profit)

            drawdown = peak - cumulative_profit
            max_drawdown = max(max_drawdown, drawdown)

        return max_drawdown
