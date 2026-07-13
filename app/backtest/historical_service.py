"""履歴CSVを使ったバックテスト実行サービス。"""

from pathlib import Path

from app.backtest.engine import BacktestEngine
from app.backtest.result import BacktestResult
from app.market.historical_csv_reader import HistoricalCsvReader
from app.strategy.opening_range_breakout import (
    OpeningRangeBreakoutStrategy,
)


class HistoricalOrbBacktestService:
    """複数の履歴CSVへORB戦略を適用する。"""

    def __init__(
        self,
        historical_reader: HistoricalCsvReader,
        strategy: OpeningRangeBreakoutStrategy,
        engine: BacktestEngine,
    ) -> None:
        """必要な構成要素を受け取る。"""

        self.historical_reader = historical_reader
        self.strategy = strategy
        self.engine = engine

    def run(
        self,
        directory: Path,
        code: str | None = None,
    ) -> BacktestResult:
        """履歴CSVを読み込み、ORBバックテストを実行する。"""

        prices = self.historical_reader.read_directory(
            directory,
            code=code,
        )
        trades = self.strategy.generate_trades(prices)

        return self.engine.run(trades)
