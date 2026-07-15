"""複数銘柄・複数日のJ-Quants分足をSQLiteへ保存する。"""

import argparse
from datetime import date, datetime

from app.database import initialize_database
from app.logger import create_logger
from app.market.bar_aggregator import StockPriceAggregator
from app.market.bar_repository import MarketBarRepository
from app.market.jquants_batch_import import (
    JQuantsBatchImportService,
)
from app.market.jquants_downloader import (
    JQuantsMinuteDownloader,
)
from app.settings import settings

DEFAULT_CODES = [
    "7203",
    "8306",
    "6758",
    "9984",
]
DEFAULT_START_DATE = "2026-07-13"
DEFAULT_END_DATE = "2026-07-13"
DEFAULT_REQUEST_INTERVAL_SECONDS = 1.1
INTERVAL_MINUTES = 5


def parse_arguments() -> argparse.Namespace:
    """コマンドライン引数を読み込む。"""

    parser = argparse.ArgumentParser(
        description=(
            "複数銘柄・複数日のJ-Quants分足を5分足へ変換してSQLiteへ保存します。"
        )
    )

    parser.add_argument(
        "--codes",
        nargs="+",
        default=DEFAULT_CODES,
        help=("取得する銘柄コード。例: --codes 7203 8306 6758"),
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

    parser.add_argument(
        "--request-interval",
        type=float,
        default=DEFAULT_REQUEST_INTERVAL_SECONDS,
        help=("APIリクエスト間の待機秒数。既定値: 1.1"),
    )

    parser.add_argument(
        "--stop-on-error",
        action="store_true",
        help="1件でも取得に失敗したら処理を停止します。",
    )

    return parser.parse_args()


def parse_date(value: str) -> date:
    """YYYY-MM-DD形式の日付をdateへ変換する。"""

    try:
        return datetime.strptime(
            value,
            "%Y-%m-%d",
        ).date()
    except ValueError as error:
        raise ValueError("日付はYYYY-MM-DD形式で指定してください。") from error


def main() -> None:
    """J-Quantsの分足を複数銘柄・複数日取り込む。"""

    arguments = parse_arguments()

    print("=" * 50)
    print(f"{settings.app_name} - J-Quants Batch Import")
    print(f"Version : {settings.version}")
    print("=" * 50)

    settings.create_directories()
    initialize_database(settings.database_path)

    logger = create_logger(settings.logs_dir)

    try:
        start_date = parse_date(arguments.start_date)
        end_date = parse_date(arguments.end_date)

        service = JQuantsBatchImportService(
            downloader=JQuantsMinuteDownloader(),
            aggregator=StockPriceAggregator(),
            repository=MarketBarRepository(settings.database_path),
            request_interval_seconds=(arguments.request_interval),
        )

        def show_progress(
            completed: int,
            total: int,
            code: str,
            target_date: date,
            minute_count: int,
            failure_count: int,
        ) -> None:
            """進捗をログへ表示する。"""

            logger.info(
                "取込進捗: %d/%d code=%s date=%s minute_bars=%d failures=%d",
                completed,
                total,
                code,
                target_date,
                minute_count,
                failure_count,
            )

        result = service.run(
            codes=arguments.codes,
            start_date=start_date,
            end_date=end_date,
            interval_minutes=INTERVAL_MINUTES,
            data_source="jquants",
            continue_on_error=not arguments.stop_on_error,
            progress_callback=show_progress,
        )

    except ValueError as error:
        logger.error(
            "一括取込を実行できません: %s",
            error,
        )
        return

    logger.info(
        "一括取込完了: codes=%d dates=%d requests=%d successful=%d empty=%d failed=%d",
        result.code_count,
        result.date_count,
        result.request_count,
        result.successful_request_count,
        result.empty_request_count,
        result.failed_request_count,
    )

    logger.info(
        "取込件数: minute_bars=%d five_minute_bars=%d processed=%d",
        result.minute_bar_count,
        result.five_minute_bar_count,
        result.processed_bar_count,
    )

    repository = MarketBarRepository(settings.database_path)

    logger.info(
        "SQLite内5分足件数: %d",
        repository.count(interval_minutes=INTERVAL_MINUTES),
    )

    for failure in result.failures[:10]:
        logger.warning(
            "取得失敗: code=%s date=%s reason=%s",
            failure.code,
            failure.target_date,
            failure.message,
        )

    if len(result.failures) > 10:
        logger.warning(
            "取得失敗の残り%d件はログ表示を省略しました。",
            len(result.failures) - 10,
        )


if __name__ == "__main__":
    main()
