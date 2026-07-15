"""Watch List全体のORBパラメータ最適化処理。"""

import csv
from dataclasses import dataclass
from datetime import datetime, time
from pathlib import Path

from app.backtest.engine import BacktestEngine
from app.backtest.result import BacktestResult
from app.backtest.trade import Trade
from app.market.bar_repository import MarketBarRepository
from app.strategy.opening_range_breakout import (
    OpeningRangeBreakoutStrategy,
)


@dataclass(frozen=True, slots=True)
class WatchlistOrbParameterSet:
    """ORB最適化で検証する1組のパラメータ。"""

    opening_range_end: time
    stop_loss_rate: float
    take_profit_rate: float


@dataclass(frozen=True, slots=True)
class WatchlistOrbOptimizationResult:
    """1組のパラメータに対する最適化結果。"""

    parameters: WatchlistOrbParameterSet
    symbol_count: int
    data_symbol_count: int
    traded_symbol_count: int
    source_bar_count: int
    trades: list[Trade]
    result: BacktestResult


@dataclass(frozen=True, slots=True)
class WatchlistOrbOptimizationReport:
    """Watch List全体のORB最適化報告。"""

    start_at: datetime
    end_at: datetime
    interval_minutes: int
    codes: list[str]
    results: list[WatchlistOrbOptimizationResult]

    @property
    def combination_count(self) -> int:
        """検証したパラメータの組み合わせ数を返す。"""

        return len(self.results)

    @property
    def best_result(
        self,
    ) -> WatchlistOrbOptimizationResult | None:
        """ランキング1位の結果を返す。"""

        if not self.results:
            return None

        return self.results[0]


class WatchlistOrbOptimizer:
    """SQLiteのWatch ListデータでORB条件を総当たりする。"""

    def __init__(
        self,
        repository: MarketBarRepository,
        engine: BacktestEngine,
        *,
        quantity: int = 100,
        force_exit_time: time = time(14, 50),
        commission: float = 0.0,
        slippage_rate: float = 0.0005,
        min_opening_range_volume: int | None = None,
        min_breakout_volume: int | None = None,
        breakout_volume_ratio: float | None = None,
        min_price: float | None = None,
        max_price: float | None = None,
        min_opening_range_turnover: float | None = None,
        min_breakout_turnover: float | None = None,
    ) -> None:
        """最適化で固定する共通条件を設定する。"""

        if quantity <= 0:
            raise ValueError("数量は0より大きい必要があります。")

        if commission < 0:
            raise ValueError("手数料は0以上である必要があります。")

        if slippage_rate < 0:
            raise ValueError("スリッページ率は0以上である必要があります。")

        self.repository = repository
        self.engine = engine

        self.quantity = quantity
        self.force_exit_time = force_exit_time
        self.commission = commission
        self.slippage_rate = slippage_rate

        self.min_opening_range_volume = min_opening_range_volume
        self.min_breakout_volume = min_breakout_volume
        self.breakout_volume_ratio = breakout_volume_ratio

        self.min_price = min_price
        self.max_price = max_price

        self.min_opening_range_turnover = min_opening_range_turnover
        self.min_breakout_turnover = min_breakout_turnover

    def run(
        self,
        codes: list[str],
        interval_minutes: int,
        start_at: datetime,
        end_at: datetime,
        opening_range_ends: list[time],
        stop_loss_rates: list[float],
        take_profit_rates: list[float],
    ) -> WatchlistOrbOptimizationReport:
        """全パラメータの組み合わせを検証する。"""

        normalized_codes = self._normalize_codes(codes)

        if interval_minutes <= 0:
            raise ValueError("時間足の間隔は0より大きい必要があります。")

        if start_at > end_at:
            raise ValueError("開始日時は終了日時以前にしてください。")

        self._validate_candidates(
            opening_range_ends=opening_range_ends,
            stop_loss_rates=stop_loss_rates,
            take_profit_rates=take_profit_rates,
        )

        prices_by_code = {
            code: self.repository.read(
                code=code,
                interval_minutes=interval_minutes,
                start_at=start_at,
                end_at=end_at,
            )
            for code in normalized_codes
        }

        results: list[WatchlistOrbOptimizationResult] = []

        for opening_range_end in opening_range_ends:
            for stop_loss_rate in stop_loss_rates:
                for take_profit_rate in take_profit_rates:
                    result = self._run_parameter_set(
                        codes=normalized_codes,
                        prices_by_code=prices_by_code,
                        opening_range_end=opening_range_end,
                        stop_loss_rate=stop_loss_rate,
                        take_profit_rate=take_profit_rate,
                    )

                    results.append(result)

        results.sort(
            key=self._ranking_key,
            reverse=True,
        )

        return WatchlistOrbOptimizationReport(
            start_at=start_at,
            end_at=end_at,
            interval_minutes=interval_minutes,
            codes=normalized_codes,
            results=results,
        )

    def _run_parameter_set(
        self,
        codes: list[str],
        prices_by_code: dict[str, list],
        opening_range_end: time,
        stop_loss_rate: float,
        take_profit_rate: float,
    ) -> WatchlistOrbOptimizationResult:
        """1組のパラメータをWatch List全体で検証する。"""

        strategy = OpeningRangeBreakoutStrategy(
            quantity=self.quantity,
            opening_range_end=opening_range_end,
            stop_loss_rate=stop_loss_rate,
            take_profit_rate=take_profit_rate,
            force_exit_time=self.force_exit_time,
            commission=self.commission,
            slippage_rate=self.slippage_rate,
            min_opening_range_volume=(self.min_opening_range_volume),
            min_breakout_volume=self.min_breakout_volume,
            breakout_volume_ratio=self.breakout_volume_ratio,
            min_price=self.min_price,
            max_price=self.max_price,
            min_opening_range_turnover=(self.min_opening_range_turnover),
            min_breakout_turnover=(self.min_breakout_turnover),
        )

        all_trades: list[Trade] = []
        data_symbol_count = 0
        traded_symbol_count = 0
        source_bar_count = 0

        for code in codes:
            prices = prices_by_code[code]
            source_bar_count += len(prices)

            if not prices:
                continue

            data_symbol_count += 1

            trades = strategy.generate_trades(prices)

            if trades:
                traded_symbol_count += 1
                all_trades.extend(trades)

        all_trades.sort(
            key=lambda trade: (
                trade.entry_at or datetime.min,
                trade.code,
            )
        )

        backtest_result = self.engine.run(all_trades)

        return WatchlistOrbOptimizationResult(
            parameters=WatchlistOrbParameterSet(
                opening_range_end=opening_range_end,
                stop_loss_rate=stop_loss_rate,
                take_profit_rate=take_profit_rate,
            ),
            symbol_count=len(codes),
            data_symbol_count=data_symbol_count,
            traded_symbol_count=traded_symbol_count,
            source_bar_count=source_bar_count,
            trades=all_trades,
            result=backtest_result,
        )

    @staticmethod
    def _ranking_key(
        item: WatchlistOrbOptimizationResult,
    ) -> tuple[
        int,
        float,
        float,
        float,
        float,
        int,
    ]:
        """最適化ランキングの並び順を返す。"""

        result = item.result

        return (
            1 if result.trade_count > 0 else 0,
            result.total_profit,
            result.profit_factor,
            result.expectancy,
            -result.max_drawdown,
            result.trade_count,
        )

    @staticmethod
    def _validate_candidates(
        opening_range_ends: list[time],
        stop_loss_rates: list[float],
        take_profit_rates: list[float],
    ) -> None:
        """最適化候補を検証する。"""

        if not opening_range_ends:
            raise ValueError("オープニングレンジ候補がありません。")

        if not stop_loss_rates:
            raise ValueError("損切り率の候補がありません。")

        if not take_profit_rates:
            raise ValueError("利確率の候補がありません。")

        if any(rate <= 0 for rate in stop_loss_rates):
            raise ValueError("損切り率はすべて0より大きい必要があります。")

        if any(rate <= 0 for rate in take_profit_rates):
            raise ValueError("利確率はすべて0より大きい必要があります。")

    @staticmethod
    def _normalize_codes(
        codes: list[str],
    ) -> list[str]:
        """銘柄コードを検証し重複を除去する。"""

        if not codes:
            raise ValueError("銘柄コードを1件以上指定してください。")

        normalized_codes: list[str] = []

        for code in codes:
            normalized = code.strip()

            if not normalized.isdigit():
                raise ValueError("銘柄コードは数字で指定してください。")

            if len(normalized) not in (4, 5):
                raise ValueError("銘柄コードは4桁または5桁で指定してください。")

            if normalized not in normalized_codes:
                normalized_codes.append(normalized)

        return normalized_codes


class WatchlistOrbOptimizationWriter:
    """ORB最適化ランキングをCSVへ出力する。"""

    def write_ranking(
        self,
        report: WatchlistOrbOptimizationReport,
        file_path: Path,
    ) -> Path:
        """最適化結果をランキング順で保存する。"""

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
                    "opening_range_end",
                    "stop_loss_rate",
                    "take_profit_rate",
                    "symbol_count",
                    "data_symbol_count",
                    "traded_symbol_count",
                    "source_bar_count",
                    "trade_count",
                    "win_count",
                    "loss_count",
                    "breakeven_count",
                    "win_rate",
                    "total_profit",
                    "gross_profit",
                    "gross_loss",
                    "average_profit",
                    "profit_factor",
                    "expectancy",
                    "max_drawdown",
                ]
            )

            for rank, item in enumerate(
                report.results,
                start=1,
            ):
                result = item.result
                parameters = item.parameters

                writer.writerow(
                    [
                        rank,
                        parameters.opening_range_end.strftime("%H:%M"),
                        parameters.stop_loss_rate,
                        parameters.take_profit_rate,
                        item.symbol_count,
                        item.data_symbol_count,
                        item.traded_symbol_count,
                        item.source_bar_count,
                        result.trade_count,
                        result.win_count,
                        result.loss_count,
                        result.breakeven_count,
                        result.win_rate,
                        result.total_profit,
                        result.gross_profit,
                        result.gross_loss,
                        result.average_profit,
                        result.profit_factor,
                        result.expectancy,
                        result.max_drawdown,
                    ]
                )

        return file_path
