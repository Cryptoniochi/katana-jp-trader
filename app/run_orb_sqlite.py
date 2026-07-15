"""SQLiteに保存した5分足でORBバックテストを実行する。"""

import argparse
from datetime import datetime, time
from math import isinf

from app.backtest.engine import BacktestEngine
from app.backtest.report_writer import BacktestReportWriter
from app.backtest.sqlite_service import (
    SqliteOrbBacktestService,
)
from app.database import initialize_database
from app.logger import create_logger
from app.market.bar_repository import MarketBarRepository
from app.settings import settings
from app.strategy.opening_range_breakout import (
    OpeningRangeBreakoutStrategy,
)

DEFAULT_CODE = "7203"
DEFAULT_START_DATE = "2026-07-13"
DEFAULT_END_DATE = "2026-07-13"
INTERVAL_MINUTES = 5


def parse_arguments() -> argparse.Namespace:
    """コマンドライン引数を読み込む。"""

    parser = argparse.ArgumentParser(
        description=("SQLiteの5分足を使ってORBバックテストを実行します。")
    )

    parser.add_argument(
        "--code",
        default=DEFAULT_CODE,
        help="銘柄コード。既定値: 7203",
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
    """日付文字列を当日開始日時へ変換する。"""

    try:
        parsed_date = datetime.strptime(
            value,
            "%Y-%m-%d",
        )
    except ValueError as error:
        raise ValueError("日付はYYYY-MM-DD形式で指定してください。") from error

    return parsed_date.replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )


def parse_date_end(value: str) -> datetime:
    """日付文字列を当日終了日時へ変換する。"""

    try:
        parsed_date = datetime.strptime(
            value,
            "%Y-%m-%d",
        )
    except ValueError as error:
        raise ValueError("日付はYYYY-MM-DD形式で指定してください。") from error

    return parsed_date.replace(
        hour=23,
        minute=59,
        second=59,
        microsecond=999999,
    )


def format_profit_factor(value: float) -> str:
    """PFをログ表示用の文字列へ変換する。"""

    if isinf(value):
        return "INF"

    return f"{value:.2f}"


def main() -> None:
    """SQLite由来のORBバックテストを実行する。"""

    arguments = parse_arguments()

    print("=" * 50)
    print(f"{settings.app_name} - SQLite ORB Backtest")
    print(f"Version : {settings.version}")
    print("=" * 50)

    settings.create_directories()
    initialize_database(settings.database_path)

    logger = create_logger(settings.logs_dir)

    try:
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
        )

        service = SqliteOrbBacktestService(
            repository=MarketBarRepository(settings.database_path),
            strategy=strategy,
            engine=BacktestEngine(),
        )

        report = service.run(
            code=arguments.code,
            interval_minutes=INTERVAL_MINUTES,
            start_at=start_at,
            end_at=end_at,
        )

    except ValueError as error:
        logger.error(
            "SQLite ORBバックテストを実行できません: %s",
            error,
        )
        return

    result = report.result

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    report_path = settings.reports_dir / (f"orb_sqlite_{report.code}_{timestamp}.csv")

    BacktestReportWriter().write_trades(
        trades=report.trades,
        file_path=report_path,
    )

    logger.info(
        "SQLiteデータを読み込みました。code=%s interval=%d bars=%d start=%s end=%s",
        report.code,
        report.interval_minutes,
        report.source_bar_count,
        report.start_at,
        report.end_at,
    )

    logger.info(
        "ORB結果: trades=%d wins=%d losses=%d breakeven=%d win_rate=%.2f%%",
        result.trade_count,
        result.win_count,
        result.loss_count,
        result.breakeven_count,
        result.win_rate,
    )

    logger.info(
        "ORB損益: total=%.2f gross_profit=%.2f gross_loss=%.2f average=%.2f",
        result.total_profit,
        result.gross_profit,
        result.gross_loss,
        result.average_profit,
    )

    logger.info(
        "ORB指標: PF=%s expectancy=%.2f max_drawdown=%.2f",
        format_profit_factor(result.profit_factor),
        result.expectancy,
        result.max_drawdown,
    )

    logger.info(
        "取引明細を出力しました。path=%s",
        report_path,
    )

    if result.trade_count == 0:
        logger.warning(
            "指定期間ではORB取引が0件でした。"
            "これは戦略条件を満たすブレイクが"
            "なかった場合の正常な結果です。"
        )


if __name__ == "__main__":
    main()
