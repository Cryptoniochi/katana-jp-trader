"""ポートフォリオ履歴から資産曲線と運用成績を算出する。"""

from typing import Protocol

from app.trading.equity_curve_models import (
    EquityCurvePoint,
    EquityCurveReport,
)
from app.trading.portfolio_models import PortfolioSnapshot


class PortfolioHistoryReader(Protocol):
    """ポートフォリオ履歴取得処理のインターフェース。"""

    def list_recent(
        self,
        *,
        limit: int = 100,
    ) -> list[PortfolioSnapshot]:
        """ポートフォリオ履歴を新しい順に返す。"""


class EquityCurveService:
    """保存済みポートフォリオ履歴を運用成績へ変換する。"""

    def __init__(
        self,
        *,
        portfolio_repository: PortfolioHistoryReader,
    ) -> None:
        """PortfolioRepositoryを設定する。"""

        self.portfolio_repository = portfolio_repository

    def create_report(
        self,
        *,
        limit: int = 10_000,
    ) -> EquityCurveReport:
        """指定件数までの履歴から運用成績を作成する。"""

        if limit <= 0:
            raise ValueError(
                "取得件数は0より大きい必要があります。"
            )

        recent_snapshots = (
            self.portfolio_repository.list_recent(
                limit=limit,
            )
        )

        snapshots = sorted(
            recent_snapshots,
            key=lambda item: item.generated_at,
        )

        if not snapshots:
            return EquityCurveReport(
                points=(),
                initial_equity=0.0,
                final_equity=0.0,
                absolute_profit_loss=0.0,
                total_return=0.0,
                maximum_drawdown=0.0,
                maximum_drawdown_amount=0.0,
                winning_period_count=0,
                losing_period_count=0,
                flat_period_count=0,
            )

        initial_equity = snapshots[0].broker_equity

        points: list[EquityCurvePoint] = []
        previous_equity: float | None = None
        peak_equity = initial_equity
        maximum_drawdown = 0.0
        maximum_drawdown_amount = 0.0
        winning_period_count = 0
        losing_period_count = 0
        flat_period_count = 0

        for snapshot in snapshots:
            equity = snapshot.broker_equity

            if previous_equity is None:
                period_return = None
            elif previous_equity == 0:
                period_return = 0.0
            else:
                period_return = (
                    equity / previous_equity
                ) - 1.0

                if period_return > 0:
                    winning_period_count += 1
                elif period_return < 0:
                    losing_period_count += 1
                else:
                    flat_period_count += 1

            cumulative_return = (
                0.0
                if initial_equity == 0
                else equity / initial_equity - 1.0
            )

            peak_equity = max(
                peak_equity,
                equity,
            )

            drawdown_amount = max(
                0.0,
                peak_equity - equity,
            )

            drawdown = (
                0.0
                if peak_equity == 0
                else drawdown_amount / peak_equity
            )

            maximum_drawdown = max(
                maximum_drawdown,
                drawdown,
            )

            maximum_drawdown_amount = max(
                maximum_drawdown_amount,
                drawdown_amount,
            )

            points.append(
                EquityCurvePoint(
                    generated_at=snapshot.generated_at,
                    equity=equity,
                    cash_balance=snapshot.cash_balance,
                    market_value=(
                        snapshot.total_market_value
                    ),
                    realized_profit_loss=(
                        snapshot.total_realized_profit_loss
                    ),
                    unrealized_profit_loss=(
                        snapshot.total_unrealized_profit_loss
                    ),
                    period_return=period_return,
                    cumulative_return=cumulative_return,
                )
            )

            previous_equity = equity

        final_equity = points[-1].equity
        absolute_profit_loss = (
            final_equity - initial_equity
        )

        total_return = (
            0.0
            if initial_equity == 0
            else absolute_profit_loss / initial_equity
        )

        return EquityCurveReport(
            points=tuple(points),
            initial_equity=initial_equity,
            final_equity=final_equity,
            absolute_profit_loss=absolute_profit_loss,
            total_return=total_return,
            maximum_drawdown=maximum_drawdown,
            maximum_drawdown_amount=(
                maximum_drawdown_amount
            ),
            winning_period_count=winning_period_count,
            losing_period_count=losing_period_count,
            flat_period_count=flat_period_count,
        )
