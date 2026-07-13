"""取引一覧を集計する最小バックテストエンジン。"""

from app.backtest.result import BacktestResult
from app.backtest.trade import Trade


class BacktestEngine:
    """取引一覧から損益と勝敗を計算する。"""

    def run(self, trades: list[Trade]) -> BacktestResult:
        """取引一覧を集計してバックテスト結果を返す。"""

        total_profit = sum(trade.profit for trade in trades)
        win_count = sum(1 for trade in trades if trade.profit > 0)
        loss_count = sum(1 for trade in trades if trade.profit < 0)
        breakeven_count = sum(1 for trade in trades if trade.profit == 0)

        return BacktestResult(
            total_profit=total_profit,
            trade_count=len(trades),
            win_count=win_count,
            loss_count=loss_count,
            breakeven_count=breakeven_count,
        )
