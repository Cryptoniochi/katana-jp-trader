"""ORB戦略のウォークフォワード検証処理。"""

import csv
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from pathlib import Path

from app.backtest.engine import BacktestEngine
from app.backtest.result import BacktestResult
from app.backtest.trade import Trade
from app.backtest.watchlist_optimizer import (
    WatchlistOrbOptimizationResult,
    WatchlistOrbOptimizer,
)
from app.market.bar_repository import MarketBarRepository
from app.strategy.orb_profile import OrbStrategyProfile


@dataclass(frozen=True, slots=True)
class WalkForwardWindow:
    """1回分の学習期間と検証期間。"""

    window_number: int

    training_start: datetime
    training_end: datetime

    testing_start: datetime
    testing_end: datetime


@dataclass(frozen=True, slots=True)
class WalkForwardWindowResult:
    """1ウィンドウ分の最適化・検証結果。"""

    window: WalkForwardWindow

    opening_range_end: time
    stop_loss_rate: float
    take_profit_rate: float

    training_source_bar_count: int
    training_traded_symbol_count: int
    training_result: BacktestResult

    testing_source_bar_count: int
    testing_data_symbol_count: int
    testing_traded_symbol_count: int
    testing_trades: list[Trade]
    testing_result: BacktestResult


@dataclass(frozen=True, slots=True)
class WalkForwardReport:
    """ウォークフォワード検証全体の結果。"""

    codes: list[str]
    interval_minutes: int
    windows: list[WalkForwardWindowResult]
    all_testing_trades: list[Trade]
    total_testing_result: BacktestResult

    @property
    def window_count(self) -> int:
        """検証ウィンドウ数を返す。"""

        return len(self.windows)

    @property
    def traded_window_count(self) -> int:
        """検証期間で取引が発生したウィンドウ数を返す。"""

        return sum(
            1 for result in self.windows if result.testing_result.trade_count > 0
        )


class OrbWalkForwardService:
    """学習期間で最適化し、直後の未使用期間で検証する。"""

    def __init__(
        self,
        repository: MarketBarRepository,
        engine: BacktestEngine,
        profile: OrbStrategyProfile,
    ) -> None:
        """Repository、集計Engine、共通条件を受け取る。"""

        self.repository = repository
        self.engine = engine
        self.profile = profile

    def run(
        self,
        codes: list[str],
        interval_minutes: int,
        start_at: datetime,
        end_at: datetime,
        *,
        training_days: int,
        testing_days: int,
        step_days: int,
        opening_range_ends: list[time],
        stop_loss_rates: list[float],
        take_profit_rates: list[float],
    ) -> WalkForwardReport:
        """複数ウィンドウの学習・検証を実行する。"""

        normalized_codes = self._normalize_codes(codes)

        if interval_minutes <= 0:
            raise ValueError("時間足の間隔は0より大きい必要があります。")

        if start_at > end_at:
            raise ValueError("開始日時は終了日時以前にしてください。")

        if training_days <= 0:
            raise ValueError("学習日数は0より大きい必要があります。")

        if testing_days <= 0:
            raise ValueError("検証日数は0より大きい必要があります。")

        if step_days <= 0:
            raise ValueError("移動日数は0より大きい必要があります。")

        windows = self._create_windows(
            start_at=start_at,
            end_at=end_at,
            training_days=training_days,
            testing_days=testing_days,
            step_days=step_days,
        )

        if not windows:
            raise ValueError(
                "指定期間ではウォークフォワードの学習・検証ウィンドウを作成できません。"
            )

        optimizer = WatchlistOrbOptimizer(
            repository=self.repository,
            engine=self.engine,
            quantity=self.profile.quantity,
            force_exit_time=self.profile.force_exit_time,
            commission=self.profile.commission,
            slippage_rate=self.profile.slippage_rate,
            min_opening_range_volume=(self.profile.min_opening_range_volume),
            min_breakout_volume=(self.profile.min_breakout_volume),
            breakout_volume_ratio=(self.profile.breakout_volume_ratio),
            min_price=self.profile.min_price,
            max_price=self.profile.max_price,
            min_opening_range_turnover=(self.profile.min_opening_range_turnover),
            min_breakout_turnover=(self.profile.min_breakout_turnover),
        )

        window_results: list[WalkForwardWindowResult] = []
        all_testing_trades: list[Trade] = []

        for window in windows:
            optimization_report = optimizer.run(
                codes=normalized_codes,
                interval_minutes=interval_minutes,
                start_at=window.training_start,
                end_at=window.training_end,
                opening_range_ends=opening_range_ends,
                stop_loss_rates=stop_loss_rates,
                take_profit_rates=take_profit_rates,
            )

            best = optimization_report.best_result

            if best is None:
                raise RuntimeError("学習期間の最適化結果を取得できませんでした。")

            window_result = self._test_window(
                codes=normalized_codes,
                interval_minutes=interval_minutes,
                window=window,
                best_training_result=best,
            )

            window_results.append(window_result)
            all_testing_trades.extend(window_result.testing_trades)

        all_testing_trades.sort(
            key=lambda trade: (
                trade.entry_at or datetime.min,
                trade.code,
            )
        )

        return WalkForwardReport(
            codes=normalized_codes,
            interval_minutes=interval_minutes,
            windows=window_results,
            all_testing_trades=all_testing_trades,
            total_testing_result=self.engine.run(all_testing_trades),
        )

    def _test_window(
        self,
        codes: list[str],
        interval_minutes: int,
        window: WalkForwardWindow,
        best_training_result: WatchlistOrbOptimizationResult,
    ) -> WalkForwardWindowResult:
        """学習期間の最良条件を検証期間へ適用する。"""

        parameters = best_training_result.parameters

        strategy = self.profile.create_strategy(
            opening_range_end=(parameters.opening_range_end),
            stop_loss_rate=parameters.stop_loss_rate,
            take_profit_rate=parameters.take_profit_rate,
        )

        testing_trades: list[Trade] = []
        testing_source_bar_count = 0
        testing_data_symbol_count = 0
        testing_traded_symbol_count = 0

        for code in codes:
            prices = self.repository.read(
                code=code,
                interval_minutes=interval_minutes,
                start_at=window.testing_start,
                end_at=window.testing_end,
            )

            testing_source_bar_count += len(prices)

            if not prices:
                continue

            testing_data_symbol_count += 1

            trades = strategy.generate_trades(prices)

            if trades:
                testing_traded_symbol_count += 1
                testing_trades.extend(trades)

        testing_trades.sort(
            key=lambda trade: (
                trade.entry_at or datetime.min,
                trade.code,
            )
        )

        return WalkForwardWindowResult(
            window=window,
            opening_range_end=(parameters.opening_range_end),
            stop_loss_rate=parameters.stop_loss_rate,
            take_profit_rate=parameters.take_profit_rate,
            training_source_bar_count=(best_training_result.source_bar_count),
            training_traded_symbol_count=(best_training_result.traded_symbol_count),
            training_result=best_training_result.result,
            testing_source_bar_count=(testing_source_bar_count),
            testing_data_symbol_count=(testing_data_symbol_count),
            testing_traded_symbol_count=(testing_traded_symbol_count),
            testing_trades=testing_trades,
            testing_result=self.engine.run(testing_trades),
        )

    @staticmethod
    def _create_windows(
        start_at: datetime,
        end_at: datetime,
        training_days: int,
        testing_days: int,
        step_days: int,
    ) -> list[WalkForwardWindow]:
        """指定期間内に学習・検証ウィンドウを作成する。"""

        normalized_start = start_at.replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )

        normalized_end = end_at.replace(
            hour=23,
            minute=59,
            second=59,
            microsecond=999999,
        )

        windows: list[WalkForwardWindow] = []
        training_start = normalized_start
        window_number = 1

        while True:
            training_end = (
                training_start
                + timedelta(days=training_days)
                - timedelta(microseconds=1)
            )

            testing_start = training_end + timedelta(microseconds=1)

            testing_end = (
                testing_start + timedelta(days=testing_days) - timedelta(microseconds=1)
            )

            if testing_end > normalized_end:
                break

            windows.append(
                WalkForwardWindow(
                    window_number=window_number,
                    training_start=training_start,
                    training_end=training_end,
                    testing_start=testing_start,
                    testing_end=testing_end,
                )
            )

            training_start += timedelta(days=step_days)
            window_number += 1

        return windows

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


class WalkForwardReportWriter:
    """ウォークフォワード結果をCSVへ出力する。"""

    def write_windows(
        self,
        report: WalkForwardReport,
        file_path: Path,
    ) -> Path:
        """ウィンドウごとの学習・検証結果を保存する。"""

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
                    "window",
                    "training_start",
                    "training_end",
                    "testing_start",
                    "testing_end",
                    "opening_range_end",
                    "stop_loss_rate",
                    "take_profit_rate",
                    "training_source_bar_count",
                    "training_traded_symbol_count",
                    "training_trade_count",
                    "training_win_rate",
                    "training_total_profit",
                    "training_profit_factor",
                    "training_expectancy",
                    "training_max_drawdown",
                    "testing_source_bar_count",
                    "testing_data_symbol_count",
                    "testing_traded_symbol_count",
                    "testing_trade_count",
                    "testing_win_rate",
                    "testing_total_profit",
                    "testing_profit_factor",
                    "testing_expectancy",
                    "testing_max_drawdown",
                ]
            )

            for item in report.windows:
                training = item.training_result
                testing = item.testing_result

                writer.writerow(
                    [
                        item.window.window_number,
                        item.window.training_start,
                        item.window.training_end,
                        item.window.testing_start,
                        item.window.testing_end,
                        item.opening_range_end.strftime("%H:%M"),
                        item.stop_loss_rate,
                        item.take_profit_rate,
                        item.training_source_bar_count,
                        item.training_traded_symbol_count,
                        training.trade_count,
                        training.win_rate,
                        training.total_profit,
                        training.profit_factor,
                        training.expectancy,
                        training.max_drawdown,
                        item.testing_source_bar_count,
                        item.testing_data_symbol_count,
                        item.testing_traded_symbol_count,
                        testing.trade_count,
                        testing.win_rate,
                        testing.total_profit,
                        testing.profit_factor,
                        testing.expectancy,
                        testing.max_drawdown,
                    ]
                )

        return file_path
