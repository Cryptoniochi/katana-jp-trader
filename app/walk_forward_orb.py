"""Watch List全体のORBウォークフォワード検証を実行する。"""

import argparse
from datetime import datetime, time
from math import isinf
from pathlib import Path

from app.backtest.engine import BacktestEngine
from app.backtest.report_writer import BacktestReportWriter
from app.backtest.walk_forward import (
    OrbWalkForwardService,
    WalkForwardReportWriter,
)
from app.database import initialize_database
from app.logger import create_logger
from app.market.bar_repository import MarketBarRepository
from app.settings import settings
from app.strategy.orb_profile import DEFAULT_ORB_PROFILE
from app.watchlist import WatchlistError, load_watchlist

DEFAULT_START_DATE = "2026-07-01"
DEFAULT_END_DATE = "2026-07-15"
DEFAULT_TRAINING_DAYS = 7
DEFAULT_TESTING_DAYS = 3
DEFAULT_STEP_DAYS = 3
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
        description=("学習期間でORB条件を最適化し、直後の未使用期間で検証します。")
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

    parser.add_argument(
        "--training-days",
        type=int,
        default=DEFAULT_TRAINING_DAYS,
    )

    parser.add_argument(
        "--testing-days",
        type=int,
        default=DEFAULT_TESTING_DAYS,
    )

    parser.add_argument(
        "--step-days",
        type=int,
        default=DEFAULT_STEP_DAYS,
    )

    return parser.parse_args()


def parse_date_start(value: str) -> datetime:
    """日付を当日の開始日時へ変換する。"""

    try:
        return datetime.strptime(
            value,
            "%Y-%m-%d",
        )
    except ValueError as error:
        raise ValueError("日付はYYYY-MM-DD形式で指定してください。") from error


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
    """PFをログ表示用文字列へ変換する。"""

    if isinf(value):
        return "INF"

    return f"{value:.2f}"


def main() -> None:
    """ORBウォークフォワード検証を実行する。"""

    arguments = parse_arguments()

    print("=" * 50)
    print(f"{settings.app_name} - ORB Walk Forward")
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

        report = OrbWalkForwardService(
            repository=MarketBarRepository(settings.database_path),
            engine=BacktestEngine(),
            profile=DEFAULT_ORB_PROFILE,
        ).run(
            codes=codes,
            interval_minutes=INTERVAL_MINUTES,
            start_at=start_at,
            end_at=end_at,
            training_days=arguments.training_days,
            testing_days=arguments.testing_days,
            step_days=arguments.step_days,
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
            "ORBウォークフォワード検証を実行できません: %s",
            error,
        )
        return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    windows_path = settings.reports_dir / f"orb_walk_forward_{timestamp}.csv"
    trades_path = settings.reports_dir / f"orb_walk_forward_trades_{timestamp}.csv"

    WalkForwardReportWriter().write_windows(
        report=report,
        file_path=windows_path,
    )

    BacktestReportWriter().write_trades(
        trades=report.all_testing_trades,
        file_path=trades_path,
    )

    logger.info(
        "Walk Forward対象を読み込みました。source=%s codes=%d",
        code_source,
        len(codes),
    )

    logger.info(
        "Walk Forward完了: windows=%d traded_windows=%d testing_trades=%d",
        report.window_count,
        report.traded_window_count,
        report.total_testing_result.trade_count,
    )

    for item in report.windows:
        training = item.training_result
        testing = item.testing_result

        logger.info(
            "WF window=%d train=%s..%s "
            "test=%s..%s opening_end=%s "
            "stop=%.2f%% target=%.2f%% "
            "train_trades=%d train_total=%.2f "
            "train_PF=%s test_trades=%d "
            "test_total=%.2f test_PF=%s "
            "test_expectancy=%.2f test_DD=%.2f",
            item.window.window_number,
            item.window.training_start.date(),
            item.window.training_end.date(),
            item.window.testing_start.date(),
            item.window.testing_end.date(),
            item.opening_range_end.strftime("%H:%M"),
            item.stop_loss_rate * 100,
            item.take_profit_rate * 100,
            training.trade_count,
            training.total_profit,
            format_profit_factor(training.profit_factor),
            testing.trade_count,
            testing.total_profit,
            format_profit_factor(testing.profit_factor),
            testing.expectancy,
            testing.max_drawdown,
        )

    total = report.total_testing_result

    logger.info(
        "アウト・オブ・サンプル合計: "
        "trades=%d wins=%d losses=%d "
        "win_rate=%.2f%% total=%.2f PF=%s "
        "expectancy=%.2f DD=%.2f",
        total.trade_count,
        total.win_count,
        total.loss_count,
        total.win_rate,
        total.total_profit,
        format_profit_factor(total.profit_factor),
        total.expectancy,
        total.max_drawdown,
    )

    logger.info(
        "Walk Forward結果を出力しました。path=%s",
        windows_path,
    )
    logger.info(
        "検証期間の取引明細を出力しました。path=%s",
        trades_path,
    )

    if total.trade_count == 0:
        logger.warning(
            "検証期間の取引が0件です。保存期間を増やしてから再評価してください。"
        )


if __name__ == "__main__":
    main()
