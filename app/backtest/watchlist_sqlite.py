"""Watch List銘柄をSQLiteから一括バックテストする処理。"""

import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.backtest.engine import BacktestEngine
from app.backtest.result import BacktestResult
from app.backtest.trade import Trade
from app.market.bar_repository import MarketBarRepository
from app.strategy.opening_range_breakout import (
    OpeningRangeBreakoutStrategy,
)


@dataclass(frozen=True, slots=True)
class WatchlistSymbolBacktestResult:
    """Watch List内の1銘柄分のバックテスト結果。"""

    code: str
    source_bar_count: int
    trades: list[Trade]
    result: BacktestResult


@dataclass(frozen=True, slots=True)
class WatchlistBacktestReport:
    """Watch List全体のバックテスト結果。"""

    start_at: datetime
    end_at: datetime
    interval_minutes: int
    symbol_results: list[WatchlistSymbolBacktestResult]
    all_trades: list[Trade]
    total_result: BacktestResult

    @property
    def symbol_count(self) -> int:
        """対象銘柄数を返す。"""

        return len(self.symbol_results)

    @property
    def data_symbol_count(self) -> int:
        """SQLiteに対象期間のデータがあった銘柄数を返す。"""

        return sum(1 for item in self.symbol_results if item.source_bar_count > 0)

    @property
    def traded_symbol_count(self) -> int:
        """1件以上の取引が発生した銘柄数を返す。"""

        return sum(1 for item in self.symbol_results if item.result.trade_count > 0)

    @property
    def missing_codes(self) -> list[str]:
        """対象期間のSQLiteデータがなかった銘柄を返す。"""

        return [item.code for item in self.symbol_results if item.source_bar_count == 0]


class WatchlistSqliteOrbBacktestService:
    """Watch List全銘柄へSQLite由来のORB戦略を適用する。"""

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
        codes: list[str],
        interval_minutes: int,
        start_at: datetime,
        end_at: datetime,
    ) -> WatchlistBacktestReport:
        """対象銘柄をSQLiteから読み込み一括検証する。"""

        normalized_codes = self._normalize_codes(codes)

        if interval_minutes <= 0:
            raise ValueError("時間足の間隔は0より大きい必要があります。")

        if start_at > end_at:
            raise ValueError("開始日時は終了日時以前にしてください。")

        symbol_results: list[WatchlistSymbolBacktestResult] = []
        all_trades: list[Trade] = []

        for code in normalized_codes:
            prices = self.repository.read(
                code=code,
                interval_minutes=interval_minutes,
                start_at=start_at,
                end_at=end_at,
            )

            trades = self.strategy.generate_trades(prices) if prices else []
            result = self.engine.run(trades)

            symbol_results.append(
                WatchlistSymbolBacktestResult(
                    code=code,
                    source_bar_count=len(prices),
                    trades=trades,
                    result=result,
                )
            )
            all_trades.extend(trades)

        all_trades.sort(
            key=lambda trade: (
                trade.entry_at or datetime.min,
                trade.code,
            )
        )

        total_result = self.engine.run(all_trades)

        symbol_results.sort(
            key=self._ranking_key,
            reverse=True,
        )

        return WatchlistBacktestReport(
            start_at=start_at,
            end_at=end_at,
            interval_minutes=interval_minutes,
            symbol_results=symbol_results,
            all_trades=all_trades,
            total_result=total_result,
        )

    @staticmethod
    def _ranking_key(
        item: WatchlistSymbolBacktestResult,
    ) -> tuple[
        int,
        float,
        float,
        float,
        str,
    ]:
        """ランキング用の並び順を返す。"""

        result = item.result

        return (
            1 if result.trade_count > 0 else 0,
            result.total_profit,
            result.profit_factor,
            -result.max_drawdown,
            item.code,
        )

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


class WatchlistBacktestReportWriter:
    """Watch Listバックテスト結果をCSVへ出力する。"""

    def write_ranking(
        self,
        report: WatchlistBacktestReport,
        file_path: Path,
    ) -> Path:
        """銘柄別ランキングをCSVへ保存する。"""

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
                report.symbol_results,
                start=1,
            ):
                result = item.result

                writer.writerow(
                    [
                        rank,
                        item.code,
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
