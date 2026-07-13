"""CSVデータを使ったバックテスト実行サービス。"""

from pathlib import Path

from app.backtest.engine import BacktestEngine
from app.backtest.result import BacktestResult
from app.market.csv_reader import CsvStockReader
from app.strategy.buy_open_sell_close import BuyOpenSellCloseStrategy


class CsvBacktestService:
    """CSVを読み込み、戦略とバックテストを一括実行する。"""

    def __init__(
        self,
        csv_reader: CsvStockReader,
        strategy: BuyOpenSellCloseStrategy,
        engine: BacktestEngine,
    ) -> None:
        """必要な構成要素を受け取る。"""

        self.csv_reader = csv_reader
        self.strategy = strategy
        self.engine = engine

    def run(self, csv_path: Path) -> BacktestResult:
        """指定したCSVファイルでバックテストを実行する。"""

        prices = self.csv_reader.read(csv_path)
        trades = self.strategy.generate_trades(prices)

        return self.engine.run(trades)
