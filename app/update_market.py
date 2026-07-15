"""SQLiteの最新保存日からJ-Quants市場データを差分更新する。"""

import argparse
from datetime import date, datetime, timedelta

from app.database import initialize_database
from app.logger import create_logger
from app.market.bar_aggregator import StockPriceAggregator
from app.market.bar_repository import MarketBarRepository
from app.market.incremental_update import (
    IncrementalMarketUpdateService,
)
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
DEFAULT_INITIAL_START_DATE = "2026-07-01"
DEFAULT_REQUEST_INTERVAL_SECONDS = 1.1
INTERVAL_MINUTES = 5


def default_end_date() -> str:
    """既定の更新終了日として前日を返す。"""

    return (date.today() - timedelta(days=1)).isoformat()


def parse_arguments() -> argparse.Namespace:
    """コマンドライン引数を読み込む。"""

    parser = argparse.ArgumentParser(
        description=("SQLiteの最新保存日の翌日からJ-Quants市場データを差分更新します。")
    )

    parser.add_argument(
        "--codes",
        nargs="+",
        default=DEFAULT_CODES,
        help=("更新する銘柄コード。例: --codes 7203 8306 6758"),
    )

    parser.add_argument(
        "--initial-start-date",
        default=DEFAULT_INITIAL_START_DATE,
        help=("未保存銘柄の初回取得開始日。形式: YYYY-MM-DD"),
    )

    parser.add_argument(
        "--end-date",
        default=default_end_date(),
        help=("更新終了日。形式: YYYY-MM-DD。既定値は前日です。"),
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
        help="取得失敗が発生した時点で処理を停止します。",
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
    """J-Quants市場データを差分更新する。"""

    arguments = parse_arguments()

    print("=" * 50)
    print(f"{settings.app_name} - Incremental Market Update")
    print(f"Version : {settings.version}")
    print("=" * 50)

    settings.create_directories()
    initialize_database(settings.database_path)

    logger = create_logger(settings.logs_dir)
    repository = MarketBarRepository(settings.database_path)

    try:
        initial_start_date = parse_date(arguments.initial_start_date)
        end_date = parse_date(arguments.end_date)

        batch_importer = JQuantsBatchImportService(
            downloader=JQuantsMinuteDownloader(),
            aggregator=StockPriceAggregator(),
            repository=repository,
            request_interval_seconds=(arguments.request_interval),
        )

        update_service = IncrementalMarketUpdateService(
            repository=repository,
            batch_importer=batch_importer,
        )

        result = update_service.run(
            codes=arguments.codes,
            initial_start_date=initial_start_date,
            end_date=end_date,
            interval_minutes=INTERVAL_MINUTES,
            data_source="jquants",
            continue_on_error=not arguments.stop_on_error,
        )

    except ValueError as error:
        logger.error(
            "市場データ差分更新を実行できません: %s",
            error,
        )
        return

    for code_result in result.code_results:
        if code_result.skipped:
            logger.info(
                "更新不要: code=%s latest=%s end=%s",
                code_result.code,
                code_result.previous_latest_date,
                code_result.end_date,
            )
            continue

        logger.info(
            "差分更新: code=%s previous_latest=%s "
            "start=%s end=%s requests=%d "
            "successful=%d empty=%d failed=%d "
            "minute_bars=%d five_minute_bars=%d "
            "processed=%d",
            code_result.code,
            code_result.previous_latest_date,
            code_result.start_date,
            code_result.end_date,
            code_result.request_count,
            code_result.successful_request_count,
            code_result.empty_request_count,
            code_result.failed_request_count,
            code_result.minute_bar_count,
            code_result.five_minute_bar_count,
            code_result.processed_bar_count,
        )

    logger.info(
        "差分更新完了: codes=%d updated=%d skipped=%d "
        "requests=%d successful=%d empty=%d failed=%d",
        result.code_count,
        result.updated_code_count,
        result.skipped_code_count,
        result.request_count,
        result.successful_request_count,
        result.empty_request_count,
        result.failed_request_count,
    )

    logger.info(
        "差分更新件数: minute_bars=%d five_minute_bars=%d processed=%d",
        result.minute_bar_count,
        result.five_minute_bar_count,
        result.processed_bar_count,
    )

    logger.info(
        "SQLite内5分足総数: %d",
        repository.count(interval_minutes=INTERVAL_MINUTES),
    )


if __name__ == "__main__":
    main()
