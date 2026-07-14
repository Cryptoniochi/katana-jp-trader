"""履歴CSVを使ったバックテスト実行サービス。"""

from dataclasses import dataclass
from pathlib import Path

from app.backtest.engine import BacktestEngine
from app.backtest.result import BacktestResult
from app.backtest.trade import Trade
from app.market.historical_csv_reader import HistoricalCsvReader
from app.strategy.opening_range_breakout import (
    OpeningRangeBreakoutStrategy,
)


@dataclass(frozen=True, slots=True)
class HistoricalBacktestReport:
    """取引明細と集計結果を持つバックテスト報告。"""

    trades: list[Trade]
    result: BacktestResult


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

    def run_report(
        self,
        directory: Path,
        code: str | None = None,
    ) -> HistoricalBacktestReport:
        """取引明細を含むバックテスト報告を返す。"""

        prices = self.historical_reader.read_directory(
            directory,
            code=code,
        )
        trades = self.strategy.generate_trades(prices)
        result = self.engine.run(trades)

        return HistoricalBacktestReport(
            trades=trades,
            result=result,
        )

    def run(
        self,
        directory: Path,
        code: str | None = None,
    ) -> BacktestResult:
        """従来どおり集計結果だけを返す。"""

        return self.run_report(
            directory,
            code=code,
        ).result
