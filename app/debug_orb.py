"""Watch List全銘柄についてORB除外理由を診断する。"""

import argparse
from collections import Counter
from datetime import datetime, time
from pathlib import Path

from app.database import initialize_database
from app.logger import create_logger
from app.market.bar_repository import MarketBarRepository
from app.settings import settings
from app.strategy.opening_range_breakout import (
    OpeningRangeBreakoutStrategy,
)
from app.strategy.orb_diagnostics import (
    OrbDiagnosticService,
    OrbDiagnosticWriter,
)
from app.watchlist import WatchlistError, load_watchlist

DEFAULT_START_DATE = "2026-07-01"
DEFAULT_END_DATE = "2026-07-15"
INTERVAL_MINUTES = 5


def parse_arguments() -> argparse.Namespace:
    """コマンドライン引数を読み込む。"""

    parser = argparse.ArgumentParser(
        description=(
            "Watch List全銘柄について、ORB条件のどこで除外されたか診断します。"
        )
    )

    parser.add_argument(
        "--watchlist",
        type=Path,
        default=settings.watchlist_path,
    )

    parser.add_argument(
        "--codes",
        nargs="+",
        default=None,
    )

    parser.add_argument(
        "--start-date",
        default=DEFAULT_START_DATE,
    )

    parser.add_argument(
        "--end-date",
        default=DEFAULT_END_DATE,
    )

    return parser.parse_args()


def parse_date_start(value: str) -> datetime:
    """日付を開始日時へ変換する。"""

    try:
        return datetime.strptime(
            value,
            "%Y-%m-%d",
        )
    except ValueError as error:
        raise ValueError("日付はYYYY-MM-DD形式で指定してください。") from error


def parse_date_end(value: str) -> datetime:
    """日付を終了日時へ変換する。"""

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
) -> list[str]:
    """診断対象の銘柄を決定する。"""

    if command_codes:
        return command_codes

    return load_watchlist(watchlist_path)


def main() -> None:
    """SQLiteの5分足を使ってORB診断を実行する。"""

    arguments = parse_arguments()

    print("=" * 50)
    print(f"{settings.app_name} - ORB Diagnostics")
    print(f"Version : {settings.version}")
    print("=" * 50)

    settings.create_directories()
    initialize_database(settings.database_path)

    logger = create_logger(settings.logs_dir)

    try:
        codes = resolve_codes(
            command_codes=arguments.codes,
            watchlist_path=arguments.watchlist,
        )
        start_at = parse_date_start(arguments.start_date)
        end_at = parse_date_end(arguments.end_date)

        repository = MarketBarRepository(settings.database_path)

        prices = []

        for code in codes:
            prices.extend(
                repository.read(
                    code=code,
                    interval_minutes=INTERVAL_MINUTES,
                    start_at=start_at,
                    end_at=end_at,
                )
            )

        if not prices:
            raise ValueError("対象期間の5分足がSQLiteにありません。")

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

        report = OrbDiagnosticService(strategy).run(prices)

    except (
        FileNotFoundError,
        ValueError,
        WatchlistError,
    ) as error:
        logger.error(
            "ORB診断を実行できません: %s",
            error,
        )
        return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    daily_path = settings.reports_dir / f"orb_diagnostic_daily_{timestamp}.csv"
    summary_path = settings.reports_dir / f"orb_diagnostic_summary_{timestamp}.csv"

    writer = OrbDiagnosticWriter()
    writer.write_daily_results(
        report,
        daily_path,
    )
    writer.write_symbol_summary(
        report,
        summary_path,
    )

    reason_counts = Counter(
        result.rejection_reason or "trade_candidate" for result in report.daily_results
    )

    logger.info(
        "ORB診断完了: symbols=%d symbol_days=%d trade_candidates=%d",
        report.symbol_count,
        report.trading_day_count,
        report.trade_candidate_count,
    )

    for summary in report.symbol_summaries:
        logger.info(
            "診断 code=%s days=%d opening=%d "
            "opening_volume=%d opening_turnover=%d "
            "breakouts=%d breakout_volume=%d "
            "volume_ratio=%d breakout_turnover=%d "
            "price_range=%d exits=%d candidates=%d",
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
        )

    for reason, count in reason_counts.most_common():
        logger.info(
            "除外理由: reason=%s count=%d",
            reason,
            count,
        )

    logger.info(
        "日次診断を出力しました。path=%s",
        daily_path,
    )
    logger.info(
        "銘柄別集計を出力しました。path=%s",
        summary_path,
    )


if __name__ == "__main__":
    main()
