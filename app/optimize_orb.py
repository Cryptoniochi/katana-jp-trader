"""Watch List全体のSQLite ORBパラメータを最適化する。"""

import argparse
from datetime import datetime, time
from math import isinf
from pathlib import Path

from app.backtest.engine import BacktestEngine
from app.backtest.report_writer import BacktestReportWriter
from app.backtest.watchlist_optimizer import (
    WatchlistOrbOptimizationWriter,
    WatchlistOrbOptimizer,
)
from app.database import initialize_database
from app.logger import create_logger
from app.market.bar_repository import MarketBarRepository
from app.settings import settings
from app.strategy.orb_profile import DEFAULT_ORB_PROFILE
from app.watchlist import WatchlistError, load_watchlist

DEFAULT_START_DATE = "2026-07-01"
DEFAULT_END_DATE = "2026-07-15"
INTERVAL_MINUTES = 5

OPENING_RANGE_ENDS = [
    time(9, 5),
    time(9, 10),
    time(9, 15),
]

STOP_LOSS_RATES = [
    0.005,
    0.008,
    0.010,
    0.012,
    0.015,
]

TAKE_PROFIT_RATES = [
    0.010,
    0.015,
    0.020,
    0.030,
    0.040,
]


def parse_arguments() -> argparse.Namespace:
    """コマンドライン引数を読み込む。"""

    parser = argparse.ArgumentParser(
        description=(
            "Watch List全体についてSQLiteの5分足を使いORB条件を総当たりします。"
        )
    )

    parser.add_argument(
        "--watchlist",
        type=Path,
        default=settings.watchlist_path,
        help=(f"Watch Listのパス。既定値: {settings.watchlist_path}"),
    )

    parser.add_argument(
        "--codes",
        nargs="+",
        default=None,
        help=("直接指定する銘柄コード。指定時はWatch Listより優先します。"),
    )

    parser.add_argument(
        "--start-date",
        default=DEFAULT_START_DATE,
        help="開始日。形式: YYYY-MM-DD",
    )

    parser.add_argument(
        "--end-date",
        default=DEFAULT_END_DATE,
        help="終了日。形式: YYYY-MM-DD",
    )

    return parser.parse_args()


def parse_date_start(value: str) -> datetime:
    """日付を当日の開始日時へ変換する。"""

    try:
        parsed = datetime.strptime(
            value,
            "%Y-%m-%d",
        )
    except ValueError as error:
        raise ValueError("日付はYYYY-MM-DD形式で指定してください。") from error

    return parsed.replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )


def parse_date_end(value: str) -> datetime:
    """日付を当日の終了日時へ変換する。"""

    try:
        parsed = datetime.strptime(
            value,
            "%Y-%m-%d",
        )
    except ValueError as error:
        raise ValueError("日付はYYYY-MM-DD形式で指定してください。") from error

    return parsed.replace(
        hour=23,
        minute=59,
        second=59,
        microsecond=999999,
    )


def resolve_codes(
    command_codes: list[str] | None,
    watchlist_path: Path,
) -> tuple[list[str], str]:
    """コマンドまたはWatch Listから銘柄を決定する。"""

    if command_codes:
        return command_codes, "command"

    return (
        load_watchlist(watchlist_path),
        str(watchlist_path),
    )


def format_profit_factor(value: float) -> str:
    """PFをログ表示用の文字列へ変換する。"""

    if isinf(value):
        return "INF"

    return f"{value:.2f}"


def main() -> None:
    """Watch List全体のORB条件を最適化する。"""

    arguments = parse_arguments()

    print("=" * 50)
    print(f"{settings.app_name} - ORB Optimization")
    print(f"Version : {settings.version}")
    print("=" * 50)

    settings.create_directories()
    initialize_database(settings.database_path)

    logger = create_logger(settings.logs_dir)
    profile = DEFAULT_ORB_PROFILE

    try:
        codes, code_source = resolve_codes(
            command_codes=arguments.codes,
            watchlist_path=arguments.watchlist,
        )

        start_at = parse_date_start(arguments.start_date)
        end_at = parse_date_end(arguments.end_date)

        optimizer = WatchlistOrbOptimizer(
            repository=MarketBarRepository(settings.database_path),
            engine=BacktestEngine(),
            quantity=profile.quantity,
            force_exit_time=profile.force_exit_time,
            commission=profile.commission,
            slippage_rate=profile.slippage_rate,
            min_opening_range_volume=(profile.min_opening_range_volume),
            min_breakout_volume=(profile.min_breakout_volume),
            breakout_volume_ratio=(profile.breakout_volume_ratio),
            min_price=profile.min_price,
            max_price=profile.max_price,
            min_opening_range_turnover=(profile.min_opening_range_turnover),
            min_breakout_turnover=(profile.min_breakout_turnover),
        )

        report = optimizer.run(
            codes=codes,
            interval_minutes=INTERVAL_MINUTES,
            start_at=start_at,
            end_at=end_at,
            opening_range_ends=OPENING_RANGE_ENDS,
            stop_loss_rates=STOP_LOSS_RATES,
            take_profit_rates=TAKE_PROFIT_RATES,
        )

    except (
        FileNotFoundError,
        ValueError,
        WatchlistError,
    ) as error:
        logger.error(
            "ORB最適化を実行できません: %s",
            error,
        )
        return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    ranking_path = settings.reports_dir / f"orb_optimization_{timestamp}.csv"

    best_trades_path = (
        settings.reports_dir / f"orb_optimization_best_trades_{timestamp}.csv"
    )

    WatchlistOrbOptimizationWriter().write_ranking(
        report=report,
        file_path=ranking_path,
    )

    best = report.best_result

    if best is not None:
        BacktestReportWriter().write_trades(
            trades=best.trades,
            file_path=best_trades_path,
        )

    logger.info(
        "最適化対象を読み込みました。source=%s codes=%d",
        code_source,
        len(codes),
    )

    logger.info(
        "最適化共通条件: opening_volume=%s "
        "opening_turnover=%s breakout_volume=%s "
        "volume_ratio=%s breakout_turnover=%s "
        "price_range=%s-%s",
        profile.min_opening_range_volume,
        profile.min_opening_range_turnover,
        profile.min_breakout_volume,
        profile.breakout_volume_ratio,
        profile.min_breakout_turnover,
        profile.min_price,
        profile.max_price,
    )

    logger.info(
        "ORB最適化を完了しました。start=%s end=%s combinations=%d",
        report.start_at,
        report.end_at,
        report.combination_count,
    )

    for rank, item in enumerate(
        report.results[:10],
        start=1,
    ):
        parameters = item.parameters
        result = item.result

        logger.info(
            "最適化順位=%d opening_end=%s "
            "stop=%.2f%% target=%.2f%% "
            "symbols=%d traded_symbols=%d "
            "trades=%d win_rate=%.2f%% "
            "total=%.2f PF=%s expectancy=%.2f "
            "DD=%.2f",
            rank,
            parameters.opening_range_end.strftime("%H:%M"),
            parameters.stop_loss_rate * 100,
            parameters.take_profit_rate * 100,
            item.symbol_count,
            item.traded_symbol_count,
            result.trade_count,
            result.win_rate,
            result.total_profit,
            format_profit_factor(result.profit_factor),
            result.expectancy,
            result.max_drawdown,
        )

    logger.info(
        "最適化ランキングを出力しました。path=%s",
        ranking_path,
    )

    if best is not None:
        logger.info(
            "最良条件の取引明細を出力しました。path=%s",
            best_trades_path,
        )

        if best.result.trade_count == 0:
            logger.warning(
                "全パラメータで取引が0件です。"
                "対象期間、データ量、流動性条件を"
                "確認してください。"
            )


if __name__ == "__main__":
    main()
