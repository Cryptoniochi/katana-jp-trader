"""ORB戦略の学習期間・検証期間分割処理。"""

import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from app.backtest.engine import BacktestEngine
from app.backtest.orb_optimizer import (
    OrbOptimizationResult,
    OrbOptimizer,
)
from app.backtest.result import BacktestResult
from app.market.historical_csv_reader import HistoricalCsvReader
from app.market.models import StockPrice
from app.strategy.opening_range_breakout import (
    OpeningRangeBreakoutStrategy,
)


@dataclass(frozen=True, slots=True)
class OrbHoldoutResult:
    """学習期間と検証期間の評価結果。"""

    training_start: date
    training_end: date
    validation_start: date
    validation_end: date

    training_day_count: int
    validation_day_count: int

    best_parameters: OrbOptimizationResult
    validation_result: BacktestResult


class OrbHoldoutValidator:
    """時系列データを学習期間と検証期間へ分割する。"""

    def __init__(
        self,
        historical_reader: HistoricalCsvReader,
        optimizer: OrbOptimizer,
        engine: BacktestEngine,
        training_ratio: float = 0.7,
    ) -> None:
        """必要な構成要素と学習期間の割合を設定する。"""

        if not 0 < training_ratio < 1:
            raise ValueError("学習期間の割合は0より大きく1より小さい必要があります。")

        self.historical_reader = historical_reader
        self.optimizer = optimizer
        self.engine = engine
        self.training_ratio = training_ratio

    def run(
        self,
        directory: Path,
        stop_loss_rates: list[float],
        take_profit_rates: list[float],
        code: str | None = None,
    ) -> OrbHoldoutResult:
        """履歴CSVを分割し、学習と検証を実行する。"""

        prices = self.historical_reader.read_directory(
            directory,
            code=code,
        )

        return self.run_prices(
            prices=prices,
            stop_loss_rates=stop_loss_rates,
            take_profit_rates=take_profit_rates,
        )

    def run_prices(
        self,
        prices: list[StockPrice],
        stop_loss_rates: list[float],
        take_profit_rates: list[float],
    ) -> OrbHoldoutResult:
        """読み込み済み株価を学習期間と検証期間へ分割する。"""

        training_prices, validation_prices = self._split_prices(prices)

        optimization_results = self.optimizer.run_prices(
            prices=training_prices,
            stop_loss_rates=stop_loss_rates,
            take_profit_rates=take_profit_rates,
        )

        if not optimization_results:
            raise ValueError("最適化結果がありません。")

        best_parameters = optimization_results[0]

        validation_strategy = OpeningRangeBreakoutStrategy(
            quantity=self.optimizer.quantity,
            opening_range_end=self.optimizer.opening_range_end,
            stop_loss_rate=best_parameters.stop_loss_rate,
            take_profit_rate=best_parameters.take_profit_rate,
            force_exit_time=self.optimizer.force_exit_time,
            commission=self.optimizer.commission,
            slippage_rate=self.optimizer.slippage_rate,
        )

        validation_trades = validation_strategy.generate_trades(validation_prices)
        validation_result = self.engine.run(validation_trades)

        training_dates = sorted({price.datetime.date() for price in training_prices})
        validation_dates = sorted(
            {price.datetime.date() for price in validation_prices}
        )

        return OrbHoldoutResult(
            training_start=training_dates[0],
            training_end=training_dates[-1],
            validation_start=validation_dates[0],
            validation_end=validation_dates[-1],
            training_day_count=len(training_dates),
            validation_day_count=len(validation_dates),
            best_parameters=best_parameters,
            validation_result=validation_result,
        )

    def _split_prices(
        self,
        prices: list[StockPrice],
    ) -> tuple[list[StockPrice], list[StockPrice]]:
        """営業日単位で学習期間と検証期間に分割する。"""

        if not prices:
            raise ValueError("検証対象の株価データがありません。")

        trading_dates = sorted({price.datetime.date() for price in prices})

        if len(trading_dates) < 2:
            raise ValueError("ホールドアウト検証には2営業日以上必要です。")

        split_index = int(len(trading_dates) * self.training_ratio)

        split_index = max(1, split_index)
        split_index = min(
            split_index,
            len(trading_dates) - 1,
        )

        training_dates = set(trading_dates[:split_index])
        validation_dates = set(trading_dates[split_index:])

        training_prices = [
            price for price in prices if price.datetime.date() in training_dates
        ]
        validation_prices = [
            price for price in prices if price.datetime.date() in validation_dates
        ]

        return training_prices, validation_prices

    @staticmethod
    def write_csv(
        result: OrbHoldoutResult,
        file_path: Path,
    ) -> Path:
        """ホールドアウト検証結果をCSVへ出力する。"""

        file_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        validation = result.validation_result
        best = result.best_parameters

        with file_path.open(
            mode="w",
            encoding="utf-8-sig",
            newline="",
        ) as csv_file:
            writer = csv.writer(csv_file)

            writer.writerow(
                [
                    "training_start",
                    "training_end",
                    "validation_start",
                    "validation_end",
                    "training_day_count",
                    "validation_day_count",
                    "stop_loss_rate",
                    "take_profit_rate",
                    "training_trade_count",
                    "training_total_profit",
                    "training_profit_factor",
                    "training_expectancy",
                    "training_max_drawdown",
                    "validation_trade_count",
                    "validation_win_rate",
                    "validation_total_profit",
                    "validation_profit_factor",
                    "validation_expectancy",
                    "validation_max_drawdown",
                ]
            )

            writer.writerow(
                [
                    result.training_start.isoformat(),
                    result.training_end.isoformat(),
                    result.validation_start.isoformat(),
                    result.validation_end.isoformat(),
                    result.training_day_count,
                    result.validation_day_count,
                    best.stop_loss_rate,
                    best.take_profit_rate,
                    best.trade_count,
                    best.total_profit,
                    best.profit_factor,
                    best.expectancy,
                    best.max_drawdown,
                    validation.trade_count,
                    validation.win_rate,
                    validation.total_profit,
                    validation.profit_factor,
                    validation.expectancy,
                    validation.max_drawdown,
                ]
            )

        return file_path
