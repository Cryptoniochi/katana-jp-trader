"""複数銘柄を対象とするバックテスト処理。"""

import csv
from dataclasses import dataclass
from pathlib import Path

from app.backtest.engine import BacktestEngine
from app.backtest.result import BacktestResult
from app.backtest.trade import Trade
from app.market.historical_csv_reader import HistoricalCsvReader
from app.market.models import StockPrice
from app.strategy.opening_range_breakout import (
    OpeningRangeBreakoutStrategy,
)


@dataclass(frozen=True, slots=True)
class SymbolBacktestResult:
    """1銘柄分のバックテスト結果。"""

    code: str
    result: BacktestResult


@dataclass(frozen=True, slots=True)
class MultiSymbolBacktestReport:
    """複数銘柄のバックテスト報告。"""

    symbol_results: list[SymbolBacktestResult]
    all_trades: list[Trade]
    total_result: BacktestResult

    @property
    def symbol_count(self) -> int:
        """検証対象となった銘柄数を返す。"""

        return len(self.symbol_results)

    @property
    def traded_symbol_count(self) -> int:
        """1件以上の取引が発生した銘柄数を返す。"""

        return sum(
            1
            for symbol_result in self.symbol_results
            if symbol_result.result.trade_count > 0
        )


class MultiSymbolOrbBacktestService:
    """複数銘柄へORB戦略を適用する。"""

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
    ) -> MultiSymbolBacktestReport:
        """履歴CSVを読み込み、銘柄別に検証する。"""

        prices = self.historical_reader.read_directory(directory)

        return self.run_prices(prices)

    def run_prices(
        self,
        prices: list[StockPrice],
    ) -> MultiSymbolBacktestReport:
        """読み込み済み株価を銘柄別に検証する。"""

        if not prices:
            raise ValueError("複数銘柄バックテスト用の株価データがありません。")

        prices_by_code: dict[str, list[StockPrice]] = {}

        for price in prices:
            prices_by_code.setdefault(price.code, []).append(price)

        symbol_results: list[SymbolBacktestResult] = []
        all_trades: list[Trade] = []

        for code in sorted(prices_by_code):
            symbol_prices = prices_by_code[code]
            trades = self.strategy.generate_trades(symbol_prices)
            result = self.engine.run(trades)

            symbol_results.append(
                SymbolBacktestResult(
                    code=code,
                    result=result,
                )
            )
            all_trades.extend(trades)

        all_trades.sort(
            key=lambda trade: (
                trade.entry_at if trade.entry_at is not None else trade.exit_at,
                trade.code,
            )
        )

        total_result = self.engine.run(all_trades)

        symbol_results.sort(
            key=lambda item: (
                item.result.total_profit,
                item.result.profit_factor,
                -item.result.max_drawdown,
                item.code,
            ),
            reverse=True,
        )

        return MultiSymbolBacktestReport(
            symbol_results=symbol_results,
            all_trades=all_trades,
            total_result=total_result,
        )


class MultiSymbolBacktestReportWriter:
    """複数銘柄の集計結果をCSVへ出力する。"""

    def write_symbol_results(
        self,
        report: MultiSymbolBacktestReport,
        file_path: Path,
    ) -> Path:
        """銘柄別バックテスト結果をCSVへ保存する。"""

        file_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with file_path.open(
            mode="w",
            encoding="utf-8-sig",
            newline="",
        ) as csv_file:
            writer = csv.writer(csv_file)

            writer.writerow(
                [
                    "rank",
                    "code",
                    "trade_count",
                    "win_count",
                    "loss_count",
                    "breakeven_count",
                    "win_rate",
                    "total_profit",
                    "gross_profit",
                    "gross_loss",
                    "profit_factor",
                    "expectancy",
                    "max_drawdown",
                ]
            )

            for rank, symbol_result in enumerate(
                report.symbol_results,
                start=1,
            ):
                result = symbol_result.result

                writer.writerow(
                    [
                        rank,
                        symbol_result.code,
                        result.trade_count,
                        result.win_count,
                        result.loss_count,
                        result.breakeven_count,
                        result.win_rate,
                        result.total_profit,
                        result.gross_profit,
                        result.gross_loss,
                        result.profit_factor,
                        result.expectancy,
                        result.max_drawdown,
                    ]
                )

        return file_path
