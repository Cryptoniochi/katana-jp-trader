"""完結トレードから高度な分析指標と内訳を作成する。"""

from __future__ import annotations

from collections import defaultdict
from math import sqrt
from statistics import fmean, pstdev

from app.backtest.advanced_performance_models import (
    AdvancedPerformanceAnalytics,
    PerformanceBreakdown,
)
from app.backtest.trade_report_models import (
    BacktestTradeReport,
    CompletedBacktestTrade,
)


class AdvancedPerformanceAnalyticsService:
    """月次・銘柄別・時間帯別・決済理由別に分析する。"""

    def create(
        self,
        report: BacktestTradeReport,
    ) -> AdvancedPerformanceAnalytics:
        """Trade Reportから高度分析を作成する。"""

        trades = tuple(report.trades)

        if not trades:
            return AdvancedPerformanceAnalytics(
                trade_count=0,
                average_trade_return=None,
                trade_return_volatility=None,
                trade_sharpe_ratio=None,
                downside_deviation=None,
                payoff_ratio=None,
                average_holding_seconds=None,
                maximum_holding_seconds=None,
                monthly=(),
                by_code=(),
                by_entry_hour=(),
                by_exit_reason=(),
            )

        returns = [
            trade.return_rate
            for trade in trades
        ]
        volatility = (
            pstdev(returns)
            if len(returns) > 1
            else 0.0
        )
        average_return = fmean(returns)
        sharpe = (
            None
            if volatility == 0
            else (
                average_return
                / volatility
                * sqrt(len(returns))
            )
        )

        downside_returns = [
            min(value, 0.0)
            for value in returns
        ]
        downside_deviation = sqrt(
            fmean(
                value * value
                for value in downside_returns
            )
        )

        profits = [
            trade.net_profit_loss
            for trade in trades
            if trade.is_winner
        ]
        losses = [
            abs(trade.net_profit_loss)
            for trade in trades
            if trade.is_loser
        ]
        average_profit = (
            fmean(profits)
            if profits
            else None
        )
        average_loss = (
            fmean(losses)
            if losses
            else None
        )
        payoff_ratio = (
            None
            if (
                average_profit is None
                or average_loss in {None, 0}
            )
            else average_profit / average_loss
        )

        holding_seconds = [
            trade.holding_seconds
            for trade in trades
        ]

        return AdvancedPerformanceAnalytics(
            trade_count=len(trades),
            average_trade_return=average_return,
            trade_return_volatility=volatility,
            trade_sharpe_ratio=sharpe,
            downside_deviation=downside_deviation,
            payoff_ratio=payoff_ratio,
            average_holding_seconds=fmean(
                holding_seconds
            ),
            maximum_holding_seconds=max(
                holding_seconds
            ),
            monthly=self._group(
                trades,
                key_provider=lambda trade: (
                    trade.exited_at.strftime("%Y-%m")
                ),
            ),
            by_code=self._group(
                trades,
                key_provider=lambda trade: trade.code,
            ),
            by_entry_hour=self._group(
                trades,
                key_provider=lambda trade: (
                    f"{trade.entered_at.hour:02d}:00"
                ),
            ),
            by_exit_reason=self._group(
                trades,
                key_provider=lambda trade: (
                    trade.exit_reason or "unknown"
                ),
            ),
        )

    def _group(
        self,
        trades: tuple[CompletedBacktestTrade, ...],
        *,
        key_provider,
    ) -> tuple[PerformanceBreakdown, ...]:
        """指定Keyごとに成績を集計する。"""

        grouped: dict[
            str,
            list[CompletedBacktestTrade],
        ] = defaultdict(list)

        for trade in trades:
            grouped[str(key_provider(trade))].append(
                trade
            )

        return tuple(
            self._create_breakdown(
                key,
                tuple(grouped_trades),
            )
            for key, grouped_trades in sorted(
                grouped.items()
            )
        )

    @staticmethod
    def _create_breakdown(
        key: str,
        trades: tuple[CompletedBacktestTrade, ...],
    ) -> PerformanceBreakdown:
        """1グループ分の成績を作成する。"""

        profits = [
            trade.net_profit_loss
            for trade in trades
            if trade.is_winner
        ]
        losses = [
            abs(trade.net_profit_loss)
            for trade in trades
            if trade.is_loser
        ]
        gross_profit = sum(profits)
        gross_loss = sum(losses)
        net_profit_loss = sum(
            trade.net_profit_loss
            for trade in trades
        )
        trade_count = len(trades)
        winning_count = len(profits)
        losing_count = len(losses)
        flat_count = (
            trade_count
            - winning_count
            - losing_count
        )

        return PerformanceBreakdown(
            key=key,
            trade_count=trade_count,
            winning_trade_count=winning_count,
            losing_trade_count=losing_count,
            flat_trade_count=flat_count,
            gross_profit=gross_profit,
            gross_loss=gross_loss,
            net_profit_loss=net_profit_loss,
            win_rate=(
                None
                if trade_count == 0
                else winning_count / trade_count
            ),
            profit_factor=(
                None
                if gross_loss == 0
                else gross_profit / gross_loss
            ),
            average_profit_loss=(
                None
                if trade_count == 0
                else net_profit_loss / trade_count
            ),
        )
