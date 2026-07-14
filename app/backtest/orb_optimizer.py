"""ORB戦略のパラメータ最適化処理。"""

import csv
from dataclasses import dataclass
from datetime import time
from pathlib import Path

from app.backtest.engine import BacktestEngine
from app.market.historical_csv_reader import HistoricalCsvReader
from app.strategy.opening_range_breakout import (
    OpeningRangeBreakoutStrategy,
)


@dataclass(frozen=True, slots=True)
class OrbOptimizationResult:
    """1組のORBパラメータに対する検証結果。"""

    stop_loss_rate: float
    take_profit_rate: float

    trade_count: int
    win_rate: float

    total_profit: float
    profit_factor: float
    expectancy: float
    max_drawdown: float


class OrbOptimizer:
    """損切り率と利確率の組み合わせを総当たりする。"""

    def __init__(
        self,
        historical_reader: HistoricalCsvReader,
        engine: BacktestEngine,
        quantity: int = 100,
        opening_range_end: time = time(9, 15),
        force_exit_time: time = time(14, 50),
        commission: float = 0.0,
        slippage_rate: float = 0.0005,
    ) -> None:
        """最適化で共通して使う条件を設定する。"""

        if quantity <= 0:
            raise ValueError("数量は0より大きい必要があります。")

        if commission < 0:
            raise ValueError("手数料は0以上である必要があります。")

        if slippage_rate < 0:
            raise ValueError("スリッページ率は0以上である必要があります。")

        self.historical_reader = historical_reader
        self.engine = engine
        self.quantity = quantity
        self.opening_range_end = opening_range_end
        self.force_exit_time = force_exit_time
        self.commission = commission
        self.slippage_rate = slippage_rate

    def run(
        self,
        directory: Path,
        stop_loss_rates: list[float],
        take_profit_rates: list[float],
        code: str | None = None,
    ) -> list[OrbOptimizationResult]:
        """全パラメータの組み合わせを検証する。"""

        self._validate_rates(
            stop_loss_rates=stop_loss_rates,
            take_profit_rates=take_profit_rates,
        )

        prices = self.historical_reader.read_directory(
            directory,
            code=code,
        )

        results: list[OrbOptimizationResult] = []

        for stop_loss_rate in stop_loss_rates:
            for take_profit_rate in take_profit_rates:
                strategy = OpeningRangeBreakoutStrategy(
                    quantity=self.quantity,
                    opening_range_end=self.opening_range_end,
                    stop_loss_rate=stop_loss_rate,
                    take_profit_rate=take_profit_rate,
                    force_exit_time=self.force_exit_time,
                    commission=self.commission,
                    slippage_rate=self.slippage_rate,
                )

                trades = strategy.generate_trades(prices)
                result = self.engine.run(trades)

                results.append(
                    OrbOptimizationResult(
                        stop_loss_rate=stop_loss_rate,
                        take_profit_rate=take_profit_rate,
                        trade_count=result.trade_count,
                        win_rate=result.win_rate,
                        total_profit=result.total_profit,
                        profit_factor=result.profit_factor,
                        expectancy=result.expectancy,
                        max_drawdown=result.max_drawdown,
                    )
                )

        return sorted(
            results,
            key=lambda item: (
                item.total_profit,
                item.profit_factor,
                -item.max_drawdown,
            ),
            reverse=True,
        )

    @staticmethod
    def write_csv(
        results: list[OrbOptimizationResult],
        file_path: Path,
    ) -> Path:
        """最適化結果をCSVへランキング順で出力する。"""

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
                    "stop_loss_rate",
                    "take_profit_rate",
                    "trade_count",
                    "win_rate",
                    "total_profit",
                    "profit_factor",
                    "expectancy",
                    "max_drawdown",
                ]
            )

            for rank, result in enumerate(results, start=1):
                writer.writerow(
                    [
                        rank,
                        result.stop_loss_rate,
                        result.take_profit_rate,
                        result.trade_count,
                        result.win_rate,
                        result.total_profit,
                        result.profit_factor,
                        result.expectancy,
                        result.max_drawdown,
                    ]
                )

        return file_path

    @staticmethod
    def _validate_rates(
        stop_loss_rates: list[float],
        take_profit_rates: list[float],
    ) -> None:
        """空または不正な最適化候補を拒否する。"""

        if not stop_loss_rates:
            raise ValueError("損切り率の候補がありません。")

        if not take_profit_rates:
            raise ValueError("利確率の候補がありません。")

        if any(rate <= 0 for rate in stop_loss_rates):
            raise ValueError("損切り率はすべて0より大きい必要があります。")

        if any(rate <= 0 for rate in take_profit_rates):
            raise ValueError("利確率はすべて0より大きい必要があります。")
