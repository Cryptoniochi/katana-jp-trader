"""ORB戦略で取引候補が除外された理由を診断する。"""

import csv
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from app.market.models import StockPrice
from app.strategy.opening_range_breakout import (
    OpeningRangeBreakoutStrategy,
)


@dataclass(frozen=True, slots=True)
class OrbDailyDiagnostic:
    """1銘柄・1営業日分のORB診断結果。"""

    code: str
    trading_date: date
    bar_count: int

    opening_bar_count: int
    opening_range_high: float | None
    opening_range_volume: int
    opening_range_turnover: float
    average_opening_volume: float

    opening_range_available: bool
    opening_volume_passed: bool
    opening_turnover_passed: bool

    price_breakout_found: bool
    breakout_at: datetime | None
    breakout_price: float | None
    breakout_volume: int | None
    breakout_volume_ratio: float | None
    breakout_turnover: float | None

    breakout_volume_passed: bool
    breakout_volume_ratio_passed: bool
    breakout_turnover_passed: bool
    price_range_passed: bool
    exit_available: bool
    trade_candidate: bool

    rejection_reason: str


@dataclass(frozen=True, slots=True)
class OrbSymbolDiagnosticSummary:
    """1銘柄分のORB診断集計。"""

    code: str
    trading_day_count: int
    opening_range_count: int
    opening_volume_pass_count: int
    opening_turnover_pass_count: int
    price_breakout_count: int
    breakout_volume_pass_count: int
    breakout_volume_ratio_pass_count: int
    breakout_turnover_pass_count: int
    price_range_pass_count: int
    exit_available_count: int
    trade_candidate_count: int


@dataclass(frozen=True, slots=True)
class OrbDiagnosticReport:
    """複数銘柄のORB診断報告。"""

    daily_results: list[OrbDailyDiagnostic]
    symbol_summaries: list[OrbSymbolDiagnosticSummary]

    @property
    def symbol_count(self) -> int:
        """診断した銘柄数を返す。"""

        return len(self.symbol_summaries)

    @property
    def trading_day_count(self) -> int:
        """診断した銘柄・営業日の総数を返す。"""

        return len(self.daily_results)

    @property
    def trade_candidate_count(self) -> int:
        """最終候補となった銘柄・営業日の総数を返す。"""

        return sum(result.trade_candidate for result in self.daily_results)


class OrbDiagnosticService:
    """ORB条件を段階別に診断する。"""

    def __init__(
        self,
        strategy: OpeningRangeBreakoutStrategy,
    ) -> None:
        """診断対象のORB戦略を設定する。"""

        self.strategy = strategy

    def run(
        self,
        prices: list[StockPrice],
    ) -> OrbDiagnosticReport:
        """株価一覧を銘柄・営業日ごとに診断する。"""

        grouped_prices: dict[
            tuple[str, date],
            list[StockPrice],
        ] = defaultdict(list)

        for price in prices:
            grouped_prices[
                (
                    price.code,
                    price.datetime.date(),
                )
            ].append(price)

        daily_results = [
            self._diagnose_day(
                code=code,
                trading_date=trading_date,
                prices=daily_prices,
            )
            for (
                code,
                trading_date,
            ), daily_prices in grouped_prices.items()
        ]

        daily_results.sort(
            key=lambda item: (
                item.code,
                item.trading_date,
            )
        )

        return OrbDiagnosticReport(
            daily_results=daily_results,
            symbol_summaries=self._summarize(daily_results),
        )

    def _diagnose_day(
        self,
        code: str,
        trading_date: date,
        prices: list[StockPrice],
    ) -> OrbDailyDiagnostic:
        """1銘柄・1営業日を診断する。"""

        sorted_prices = sorted(
            prices,
            key=lambda price: price.datetime,
        )

        opening_prices = [
            price
            for price in sorted_prices
            if (price.datetime.time() <= self.strategy.opening_range_end)
        ]

        opening_bar_count = len(opening_prices)

        if not opening_prices:
            return self._create_rejected_result(
                code=code,
                trading_date=trading_date,
                bar_count=len(sorted_prices),
                rejection_reason="opening_range_unavailable",
            )

        opening_range_high = max(price.high for price in opening_prices)
        opening_range_volume = sum(price.volume for price in opening_prices)
        opening_range_turnover = sum(
            price.close * price.volume for price in opening_prices
        )
        average_opening_volume = opening_range_volume / opening_bar_count

        opening_volume_passed = (
            self.strategy.min_opening_range_volume is None
            or opening_range_volume >= self.strategy.min_opening_range_volume
        )

        if not opening_volume_passed:
            return OrbDailyDiagnostic(
                code=code,
                trading_date=trading_date,
                bar_count=len(sorted_prices),
                opening_bar_count=opening_bar_count,
                opening_range_high=opening_range_high,
                opening_range_volume=opening_range_volume,
                opening_range_turnover=opening_range_turnover,
                average_opening_volume=average_opening_volume,
                opening_range_available=True,
                opening_volume_passed=False,
                opening_turnover_passed=False,
                price_breakout_found=False,
                breakout_at=None,
                breakout_price=None,
                breakout_volume=None,
                breakout_volume_ratio=None,
                breakout_turnover=None,
                breakout_volume_passed=False,
                breakout_volume_ratio_passed=False,
                breakout_turnover_passed=False,
                price_range_passed=False,
                exit_available=False,
                trade_candidate=False,
                rejection_reason="opening_volume",
            )

        opening_turnover_passed = (
            self.strategy.min_opening_range_turnover is None
            or opening_range_turnover >= self.strategy.min_opening_range_turnover
        )

        if not opening_turnover_passed:
            return OrbDailyDiagnostic(
                code=code,
                trading_date=trading_date,
                bar_count=len(sorted_prices),
                opening_bar_count=opening_bar_count,
                opening_range_high=opening_range_high,
                opening_range_volume=opening_range_volume,
                opening_range_turnover=opening_range_turnover,
                average_opening_volume=average_opening_volume,
                opening_range_available=True,
                opening_volume_passed=True,
                opening_turnover_passed=False,
                price_breakout_found=False,
                breakout_at=None,
                breakout_price=None,
                breakout_volume=None,
                breakout_volume_ratio=None,
                breakout_turnover=None,
                breakout_volume_passed=False,
                breakout_volume_ratio_passed=False,
                breakout_turnover_passed=False,
                price_range_passed=False,
                exit_available=False,
                trade_candidate=False,
                rejection_reason="opening_turnover",
            )

        price_breakout_bars = [
            price
            for price in sorted_prices
            if (
                self.strategy.opening_range_end
                < price.datetime.time()
                < self.strategy.force_exit_time
                and price.high > opening_range_high
            )
        ]

        if not price_breakout_bars:
            return OrbDailyDiagnostic(
                code=code,
                trading_date=trading_date,
                bar_count=len(sorted_prices),
                opening_bar_count=opening_bar_count,
                opening_range_high=opening_range_high,
                opening_range_volume=opening_range_volume,
                opening_range_turnover=opening_range_turnover,
                average_opening_volume=average_opening_volume,
                opening_range_available=True,
                opening_volume_passed=True,
                opening_turnover_passed=True,
                price_breakout_found=False,
                breakout_at=None,
                breakout_price=None,
                breakout_volume=None,
                breakout_volume_ratio=None,
                breakout_turnover=None,
                breakout_volume_passed=False,
                breakout_volume_ratio_passed=False,
                breakout_turnover_passed=False,
                price_range_passed=False,
                exit_available=False,
                trade_candidate=False,
                rejection_reason="no_price_breakout",
            )

        last_failed_result: OrbDailyDiagnostic | None = None

        for breakout_bar in price_breakout_bars:
            result = self._diagnose_breakout_bar(
                code=code,
                trading_date=trading_date,
                sorted_prices=sorted_prices,
                opening_prices=opening_prices,
                opening_range_high=opening_range_high,
                opening_range_volume=opening_range_volume,
                opening_range_turnover=opening_range_turnover,
                average_opening_volume=average_opening_volume,
                breakout_bar=breakout_bar,
            )

            if result.trade_candidate:
                return result

            last_failed_result = result

        if last_failed_result is None:
            raise RuntimeError("価格ブレイク診断結果を作成できませんでした。")

        return last_failed_result

    def _diagnose_breakout_bar(
        self,
        code: str,
        trading_date: date,
        sorted_prices: list[StockPrice],
        opening_prices: list[StockPrice],
        opening_range_high: float,
        opening_range_volume: int,
        opening_range_turnover: float,
        average_opening_volume: float,
        breakout_bar: StockPrice,
    ) -> OrbDailyDiagnostic:
        """1本の価格ブレイク足を段階別に診断する。"""

        breakout_volume_ratio = (
            breakout_bar.volume / average_opening_volume
            if average_opening_volume > 0
            else 0.0
        )
        breakout_turnover = breakout_bar.close * breakout_bar.volume

        breakout_volume_passed = (
            self.strategy.min_breakout_volume is None
            or breakout_bar.volume >= self.strategy.min_breakout_volume
        )

        breakout_volume_ratio_passed = (
            self.strategy.breakout_volume_ratio is None
            or breakout_volume_ratio >= self.strategy.breakout_volume_ratio
        )

        breakout_turnover_passed = (
            self.strategy.min_breakout_turnover is None
            or breakout_turnover >= self.strategy.min_breakout_turnover
        )

        price_range_passed = (
            self.strategy.min_price is None
            or breakout_bar.close >= self.strategy.min_price
        ) and (
            self.strategy.max_price is None
            or breakout_bar.close <= self.strategy.max_price
        )

        breakout_index = sorted_prices.index(breakout_bar)

        exit_available = any(
            price.datetime.time() <= self.strategy.force_exit_time
            for price in sorted_prices[breakout_index + 1 :]
        )

        rejection_reason = self._resolve_reason(
            breakout_volume_passed=(breakout_volume_passed),
            breakout_volume_ratio_passed=(breakout_volume_ratio_passed),
            breakout_turnover_passed=(breakout_turnover_passed),
            price_range_passed=price_range_passed,
            exit_available=exit_available,
        )

        trade_candidate = rejection_reason == ""

        return OrbDailyDiagnostic(
            code=code,
            trading_date=trading_date,
            bar_count=len(sorted_prices),
            opening_bar_count=len(opening_prices),
            opening_range_high=opening_range_high,
            opening_range_volume=opening_range_volume,
            opening_range_turnover=opening_range_turnover,
            average_opening_volume=average_opening_volume,
            opening_range_available=True,
            opening_volume_passed=True,
            opening_turnover_passed=True,
            price_breakout_found=True,
            breakout_at=breakout_bar.datetime,
            breakout_price=breakout_bar.close,
            breakout_volume=breakout_bar.volume,
            breakout_volume_ratio=breakout_volume_ratio,
            breakout_turnover=breakout_turnover,
            breakout_volume_passed=breakout_volume_passed,
            breakout_volume_ratio_passed=(breakout_volume_ratio_passed),
            breakout_turnover_passed=(breakout_turnover_passed),
            price_range_passed=price_range_passed,
            exit_available=exit_available,
            trade_candidate=trade_candidate,
            rejection_reason=rejection_reason,
        )

    @staticmethod
    def _resolve_reason(
        *,
        breakout_volume_passed: bool,
        breakout_volume_ratio_passed: bool,
        breakout_turnover_passed: bool,
        price_range_passed: bool,
        exit_available: bool,
    ) -> str:
        """最初に不合格となった条件名を返す。"""

        if not breakout_volume_passed:
            return "breakout_volume"

        if not breakout_volume_ratio_passed:
            return "breakout_volume_ratio"

        if not breakout_turnover_passed:
            return "breakout_turnover"

        if not price_range_passed:
            return "price_range"

        if not exit_available:
            return "exit_unavailable"

        return ""

    @staticmethod
    def _create_rejected_result(
        code: str,
        trading_date: date,
        bar_count: int,
        rejection_reason: str,
    ) -> OrbDailyDiagnostic:
        """オープニングレンジを作れない日の結果を作る。"""

        return OrbDailyDiagnostic(
            code=code,
            trading_date=trading_date,
            bar_count=bar_count,
            opening_bar_count=0,
            opening_range_high=None,
            opening_range_volume=0,
            opening_range_turnover=0.0,
            average_opening_volume=0.0,
            opening_range_available=False,
            opening_volume_passed=False,
            opening_turnover_passed=False,
            price_breakout_found=False,
            breakout_at=None,
            breakout_price=None,
            breakout_volume=None,
            breakout_volume_ratio=None,
            breakout_turnover=None,
            breakout_volume_passed=False,
            breakout_volume_ratio_passed=False,
            breakout_turnover_passed=False,
            price_range_passed=False,
            exit_available=False,
            trade_candidate=False,
            rejection_reason=rejection_reason,
        )

    @staticmethod
    def _summarize(
        daily_results: list[OrbDailyDiagnostic],
    ) -> list[OrbSymbolDiagnosticSummary]:
        """日次診断を銘柄別に集計する。"""

        results_by_code: dict[
            str,
            list[OrbDailyDiagnostic],
        ] = defaultdict(list)

        for result in daily_results:
            results_by_code[result.code].append(result)

        summaries = [
            OrbSymbolDiagnosticSummary(
                code=code,
                trading_day_count=len(results),
                opening_range_count=sum(
                    result.opening_range_available for result in results
                ),
                opening_volume_pass_count=sum(
                    result.opening_volume_passed for result in results
                ),
                opening_turnover_pass_count=sum(
                    result.opening_turnover_passed for result in results
                ),
                price_breakout_count=sum(
                    result.price_breakout_found for result in results
                ),
                breakout_volume_pass_count=sum(
                    result.breakout_volume_passed for result in results
                ),
                breakout_volume_ratio_pass_count=sum(
                    result.breakout_volume_ratio_passed for result in results
                ),
                breakout_turnover_pass_count=sum(
                    result.breakout_turnover_passed for result in results
                ),
                price_range_pass_count=sum(
                    result.price_range_passed for result in results
                ),
                exit_available_count=sum(result.exit_available for result in results),
                trade_candidate_count=sum(result.trade_candidate for result in results),
            )
            for code, results in results_by_code.items()
        ]

        return sorted(
            summaries,
            key=lambda item: item.code,
        )


class OrbDiagnosticWriter:
    """ORB診断結果をCSVへ出力する。"""

    def write_daily_results(
        self,
        report: OrbDiagnosticReport,
        file_path: Path,
    ) -> Path:
        """銘柄・営業日別の詳細を出力する。"""

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
                    "code",
                    "trading_date",
                    "bar_count",
                    "opening_bar_count",
                    "opening_range_high",
                    "opening_range_volume",
                    "opening_range_turnover",
                    "average_opening_volume",
                    "opening_range_available",
                    "opening_volume_passed",
                    "opening_turnover_passed",
                    "price_breakout_found",
                    "breakout_at",
                    "breakout_price",
                    "breakout_volume",
                    "breakout_volume_ratio",
                    "breakout_turnover",
                    "breakout_volume_passed",
                    "breakout_volume_ratio_passed",
                    "breakout_turnover_passed",
                    "price_range_passed",
                    "exit_available",
                    "trade_candidate",
                    "rejection_reason",
                ]
            )

            for result in report.daily_results:
                writer.writerow(
                    [
                        result.code,
                        result.trading_date,
                        result.bar_count,
                        result.opening_bar_count,
                        result.opening_range_high,
                        result.opening_range_volume,
                        result.opening_range_turnover,
                        result.average_opening_volume,
                        result.opening_range_available,
                        result.opening_volume_passed,
                        result.opening_turnover_passed,
                        result.price_breakout_found,
                        result.breakout_at,
                        result.breakout_price,
                        result.breakout_volume,
                        result.breakout_volume_ratio,
                        result.breakout_turnover,
                        result.breakout_volume_passed,
                        result.breakout_volume_ratio_passed,
                        result.breakout_turnover_passed,
                        result.price_range_passed,
                        result.exit_available,
                        result.trade_candidate,
                        result.rejection_reason,
                    ]
                )

        return file_path

    def write_symbol_summary(
        self,
        report: OrbDiagnosticReport,
        file_path: Path,
    ) -> Path:
        """銘柄別の通過件数を出力する。"""

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
                    "code",
                    "trading_day_count",
                    "opening_range_count",
                    "opening_volume_pass_count",
                    "opening_turnover_pass_count",
                    "price_breakout_count",
                    "breakout_volume_pass_count",
                    "breakout_volume_ratio_pass_count",
                    "breakout_turnover_pass_count",
                    "price_range_pass_count",
                    "exit_available_count",
                    "trade_candidate_count",
                ]
            )

            for summary in report.symbol_summaries:
                writer.writerow(
                    [
                        summary.code,
                        summary.trading_day_count,
                        summary.opening_range_count,
                        summary.opening_volume_pass_count,
                        summary.opening_turnover_pass_count,
                        summary.price_breakout_count,
                        summary.breakout_volume_pass_count,
                        summary.breakout_volume_ratio_pass_count,
                        summary.breakout_turnover_pass_count,
                        summary.price_range_pass_count,
                        summary.exit_available_count,
                        summary.trade_candidate_count,
                    ]
                )

        return file_path
