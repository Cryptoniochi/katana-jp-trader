"""SQLiteの市場データを使ったバックテストサービス。"""

from dataclasses import dataclass
from datetime import datetime

from app.backtest.engine import BacktestEngine
from app.backtest.result import BacktestResult
from app.backtest.trade import Trade
from app.market.bar_repository import MarketBarRepository
from app.strategy.opening_range_breakout import (
    OpeningRangeBreakoutStrategy,
)


@dataclass(frozen=True, slots=True)
class SqliteBacktestReport:
    """SQLiteバックテストの取引明細と集計結果。"""

    code: str
    interval_minutes: int
    start_at: datetime
    end_at: datetime
    source_bar_count: int
    trades: list[Trade]
    result: BacktestResult


class SqliteOrbBacktestService:
    """SQLiteの時間足へORB戦略を適用する。"""

    def __init__(
        self,
        repository: MarketBarRepository,
        strategy: OpeningRangeBreakoutStrategy,
        engine: BacktestEngine,
    ) -> None:
        """必要な構成要素を受け取る。"""

        self.repository = repository
        self.strategy = strategy
        self.engine = engine

    def run(
        self,
        code: str,
        interval_minutes: int,
        start_at: datetime,
        end_at: datetime,
    ) -> SqliteBacktestReport:
        """指定銘柄・期間の時間足でORBを検証する。"""

        normalized_code = code.strip()

        if not normalized_code:
            raise ValueError("銘柄コードを指定してください。")

        if interval_minutes <= 0:
            raise ValueError("時間足の間隔は0より大きい必要があります。")

        if start_at > end_at:
            raise ValueError("開始日時は終了日時以前にしてください。")

        prices = self.repository.read(
            code=normalized_code,
            interval_minutes=interval_minutes,
            start_at=start_at,
            end_at=end_at,
        )

        if not prices:
            raise ValueError("指定条件に一致する時間足がSQLiteに保存されていません。")

        trades = self.strategy.generate_trades(prices)
        result = self.engine.run(trades)

        return SqliteBacktestReport(
            code=normalized_code,
            interval_minutes=interval_minutes,
            start_at=start_at,
            end_at=end_at,
            source_bar_count=len(prices),
            trades=trades,
            result=result,
        )
