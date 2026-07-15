"""Watch List全銘柄のSQLite ORBバックテストを実行する。"""

import argparse
from datetime import datetime, time
from math import isinf
from pathlib import Path

from app.backtest.engine import BacktestEngine
from app.backtest.report_writer import BacktestReportWriter
from app.backtest.watchlist_sqlite import (
    WatchlistBacktestReportWriter,
    WatchlistSqliteOrbBacktestService,
)
from app.database import initialize_database
from app.logger import create_logger
from app.market.bar_repository import MarketBarRepository
from app.settings import settings
from app.strategy.opening_range_breakout import (
    OpeningRangeBreakoutStrategy,
)
from app.watchlist import WatchlistError, load_watchlist

DEFAULT_START_DATE = "2026-07-01"
DEFAULT_END_DATE = "2026-07-15"
INTERVAL_MINUTES = 5


def parse_arguments() -> argparse.Namespace:
    """コマンドライン引数を読み込む。"""

    parser = argparse.ArgumentParser(
        description=(
            "Watch List全銘柄についてSQLiteの5分足を使ったORBバックテストを実行します。"
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
    """日付文字列を当日の開始日時へ変換する。"""

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
    """日付文字列を当日の終了日時へ変換する。"""

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
    """PFをログ表示用文字列へ変換する。"""

    if isinf(value):
        return "INF"

    return f"{value:.2f}"


def main() -> None:
    """Watch List全銘柄のORBを一括検証する。"""

    arguments = parse_arguments()

    print("=" * 50)
    print(f"{settings.app_name} - Watch List ORB Ranking")
    print(f"Version : {settings.version}")
    print("=" * 50)

    settings.create_directories()
    initialize_database(settings.database_path)

    logger = create_logger(settings.logs_dir)

    try:
        codes, code_source = resolve_codes(
            command_codes=arguments.codes,
            watchlist_path=arguments.watchlist,
        )

        start_at = parse_date_start(arguments.start_date)
        end_at = parse_date_end(arguments.end_date)

        strategy = OpeningRangeBreakoutStrategy(
            quantity=100,
            opening_range_end=time(9, 15),
            stop_loss_rate=0.01,
            take_profit_rate=0.02,
            force_exit_time=time(14, 50),
            commission=0.0,
            slippage_rate=0.0005,
            min_opening_range_volume=200_000,
            min_breakout_volume=150_000,
            breakout_volume_ratio=1.2,
            min_price=500.0,
            max_price=20_000.0,
            min_opening_range_turnover=200_000_000.0,
            min_breakout_turnover=100_000_000.0,
        )

        service = WatchlistSqliteOrbBacktestService(
            repository=MarketBarRepository(settings.database_path),
            strategy=strategy,
            engine=BacktestEngine(),
        )

        report = service.run(
            codes=codes,
            interval_minutes=INTERVAL_MINUTES,
            start_at=start_at,
            end_at=end_at,
        )

    except (
        FileNotFoundError,
        ValueError,
        WatchlistError,
    ) as error:
        logger.error(
            "Watch List ORBバックテストを実行できません: %s",
            error,
        )
        return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    ranking_path = settings.reports_dir / f"orb_watchlist_ranking_{timestamp}.csv"
    trades_path = settings.reports_dir / f"orb_watchlist_trades_{timestamp}.csv"

    WatchlistBacktestReportWriter().write_ranking(
        report=report,
        file_path=ranking_path,
    )

    BacktestReportWriter().write_trades(
        trades=report.all_trades,
        file_path=trades_path,
    )

    total = report.total_result

    logger.info(
        "Watch Listを読み込みました。source=%s codes=%d",
        code_source,
        len(codes),
    )

    logger.info(
        "SQLite一括検証: start=%s end=%s interval=%d "
        "symbols=%d data_symbols=%d traded_symbols=%d",
        report.start_at,
        report.end_at,
        report.interval_minutes,
        report.symbol_count,
        report.data_symbol_count,
        report.traded_symbol_count,
    )

    logger.info(
        "全銘柄結果: trades=%d wins=%d losses=%d breakeven=%d win_rate=%.2f%%",
        total.trade_count,
        total.win_count,
        total.loss_count,
        total.breakeven_count,
        total.win_rate,
    )

    logger.info(
        "全銘柄損益: total=%.2f gross_profit=%.2f gross_loss=%.2f average=%.2f",
        total.total_profit,
        total.gross_profit,
        total.gross_loss,
        total.average_profit,
    )

    logger.info(
        "全銘柄指標: PF=%s expectancy=%.2f max_drawdown=%.2f",
        format_profit_factor(total.profit_factor),
        total.expectancy,
        total.max_drawdown,
    )

    for rank, item in enumerate(
        report.symbol_results[:10],
        start=1,
    ):
        result = item.result

        logger.info(
            "ORB順位=%d code=%s bars=%d trades=%d "
            "win_rate=%.2f%% total=%.2f PF=%s "
            "expectancy=%.2f DD=%.2f",
            rank,
            item.code,
            item.source_bar_count,
            result.trade_count,
            result.win_rate,
            result.total_profit,
            format_profit_factor(result.profit_factor),
            result.expectancy,
            result.max_drawdown,
        )

    if report.missing_codes:
        logger.warning(
            "対象期間のSQLiteデータがない銘柄: %s",
            ", ".join(report.missing_codes),
        )

    logger.info(
        "ORBランキングを出力しました。path=%s",
        ranking_path,
    )

    logger.info(
        "ORB取引明細を出力しました。path=%s",
        trades_path,
    )


if __name__ == "__main__":
    main()
