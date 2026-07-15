"""Watch List銘柄のJ-Quants履歴分足をSQLiteへ保存する。"""

import argparse
import logging
from datetime import date, datetime
from pathlib import Path

from app.database import initialize_database
from app.logger import create_logger
from app.market.bar_aggregator import StockPriceAggregator
from app.market.bar_repository import MarketBarRepository
from app.market.history_progress import (
    HistoryImportProgress,
    HistoryImportResult,
)
from app.market.jquants_batch_import import (
    JQuantsBatchImportService,
)
from app.market.jquants_calendar import (
    JQuantsCalendarError,
    JQuantsTradingCalendarClient,
)
from app.market.jquants_downloader import (
    JQuantsDownloadError,
    JQuantsMinuteDownloader,
)
from app.market.jquants_history_importer import (
    HistoricalBatchImporter,
    JQuantsHistoryImporter,
    TradingCalendarReader,
)
from app.settings import settings
from app.watchlist import WatchlistError, load_watchlist

DEFAULT_START_DATE = "2026-01-01"
DEFAULT_END_DATE = "2026-07-15"
DEFAULT_CHUNK_BUSINESS_DAYS = 20
DEFAULT_REQUEST_INTERVAL_SECONDS = 1.1
INTERVAL_MINUTES = 5
DATA_SOURCE = "jquants"


def parse_arguments() -> argparse.Namespace:
    """コマンドライン引数を読み込む。"""

    parser = argparse.ArgumentParser(
        description=(
            "Watch Listの銘柄について、"
            "J-Quantsの履歴1分足を取得し、"
            "5分足へ集約してSQLiteへ保存します。"
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
        help="履歴取得開始日。形式: YYYY-MM-DD",
    )

    parser.add_argument(
        "--end-date",
        default=DEFAULT_END_DATE,
        help="履歴取得終了日。形式: YYYY-MM-DD",
    )

    parser.add_argument(
        "--chunk-business-days",
        type=int,
        default=DEFAULT_CHUNK_BUSINESS_DAYS,
        help=("進捗管理上の1チャンク当たり営業日数。既定値: 20"),
    )

    parser.add_argument(
        "--request-interval",
        type=float,
        default=DEFAULT_REQUEST_INTERVAL_SECONDS,
        help=("分足APIリクエスト間の待機秒数。既定値: 1.1"),
    )

    parser.add_argument(
        "--stop-on-error",
        action="store_true",
        help=("取得失敗が発生した時点で履歴取込を停止します。"),
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


def resolve_codes(
    command_codes: list[str] | None,
    watchlist_path: Path,
) -> tuple[list[str], str]:
    """コマンドまたはWatch Listから対象銘柄を決定する。"""

    if command_codes:
        return command_codes, "command"

    return (
        load_watchlist(watchlist_path),
        str(watchlist_path),
    )


def format_progress_message(
    progress: HistoryImportProgress,
) -> str:
    """進捗ログ用の文字列を作成する。"""

    return (
        "履歴取込進捗: "
        f"{progress.completed_tasks}/"
        f"{progress.total_tasks} "
        f"({progress.completion_rate:.1f}%) "
        f"code={progress.code} "
        f"chunk={progress.chunk_number}/"
        f"{progress.chunk_count} "
        f"period={progress.start_date}.."
        f"{progress.end_date} "
        f"requests={progress.request_count} "
        f"successful="
        f"{progress.successful_request_count} "
        f"empty={progress.empty_request_count} "
        f"failed={progress.failed_request_count} "
        f"minute_bars={progress.minute_bar_count} "
        f"five_minute_bars="
        f"{progress.five_minute_bar_count} "
        f"processed={progress.processed_bar_count}"
    )


def create_progress_callback(
    logger: logging.Logger,
):
    """進捗をログへ出力するコールバックを返す。"""

    def show_progress(
        progress: HistoryImportProgress,
    ) -> None:
        logger.info(
            "%s",
            format_progress_message(progress),
        )

    return show_progress


def run_history_import(
    *,
    codes: list[str],
    start_date: date,
    end_date: date,
    chunk_business_days: int,
    request_interval_seconds: float,
    continue_on_error: bool,
    calendar_reader: TradingCalendarReader | None = None,
    batch_importer: HistoricalBatchImporter | None = None,
    progress_callback=None,
) -> HistoryImportResult:
    """履歴取込を構成して実行する。"""

    if request_interval_seconds < 0:
        raise ValueError("リクエスト間隔は0秒以上で指定してください。")

    resolved_calendar_reader = calendar_reader

    if resolved_calendar_reader is None:
        resolved_calendar_reader = JQuantsTradingCalendarClient()

    resolved_batch_importer = batch_importer

    if resolved_batch_importer is None:
        repository = MarketBarRepository(settings.database_path)

        resolved_batch_importer = JQuantsBatchImportService(
            downloader=JQuantsMinuteDownloader(),
            aggregator=StockPriceAggregator(),
            repository=repository,
            request_interval_seconds=(request_interval_seconds),
        )

    importer = JQuantsHistoryImporter(
        calendar_reader=resolved_calendar_reader,
        batch_importer=resolved_batch_importer,
    )

    return importer.run(
        codes=codes,
        start_date=start_date,
        end_date=end_date,
        chunk_business_days=chunk_business_days,
        interval_minutes=INTERVAL_MINUTES,
        data_source=DATA_SOURCE,
        continue_on_error=continue_on_error,
        progress_callback=progress_callback,
    )


def log_result(
    logger: logging.Logger,
    result: HistoryImportResult,
) -> None:
    """履歴取込結果をログへ出力する。"""

    logger.info(
        "履歴取込完了: "
        "start=%s end=%s codes=%d "
        "successful_codes=%d failed_codes=%d "
        "business_dates=%d chunks=%d",
        result.start_date,
        result.end_date,
        result.code_count,
        result.successful_code_count,
        result.failed_code_count,
        result.business_date_count,
        result.chunk_count,
    )

    logger.info(
        "履歴取込リクエスト: requests=%d successful=%d empty=%d failed=%d",
        result.request_count,
        result.successful_request_count,
        result.empty_request_count,
        result.failed_request_count,
    )

    logger.info(
        "履歴取込データ: minute_bars=%d five_minute_bars=%d processed=%d",
        result.minute_bar_count,
        result.five_minute_bar_count,
        result.processed_bar_count,
    )

    for symbol_result in result.code_results:
        logger.info(
            "履歴銘柄結果: code=%s "
            "business_dates=%d chunks=%d "
            "requests=%d successful=%d "
            "empty=%d failed=%d "
            "minute_bars=%d five_minute_bars=%d "
            "processed=%d",
            symbol_result.code,
            symbol_result.business_date_count,
            symbol_result.chunk_count,
            symbol_result.request_count,
            symbol_result.successful_request_count,
            symbol_result.empty_request_count,
            symbol_result.failed_request_count,
            symbol_result.minute_bar_count,
            symbol_result.five_minute_bar_count,
            symbol_result.processed_bar_count,
        )

    for failure in result.failures[:20]:
        logger.warning(
            "履歴取得失敗: code=%s start=%s end=%s reason=%s",
            failure.code,
            failure.start_date,
            failure.end_date,
            failure.message,
        )

    if len(result.failures) > 20:
        logger.warning(
            "履歴取得失敗の残り%d件はログ表示を省略しました。",
            len(result.failures) - 20,
        )


def main() -> None:
    """Watch List銘柄の履歴データを取り込む。"""

    arguments = parse_arguments()

    print("=" * 50)
    print(f"{settings.app_name} - J-Quants Historical Import")
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

        start_date = parse_date(arguments.start_date)
        end_date = parse_date(arguments.end_date)

        logger.info(
            "履歴取込対象を読み込みました。"
            "source=%s codes=%d "
            "start=%s end=%s "
            "chunk_business_days=%d "
            "request_interval=%.2f",
            code_source,
            len(codes),
            start_date,
            end_date,
            arguments.chunk_business_days,
            arguments.request_interval,
        )

        result = run_history_import(
            codes=codes,
            start_date=start_date,
            end_date=end_date,
            chunk_business_days=(arguments.chunk_business_days),
            request_interval_seconds=(arguments.request_interval),
            continue_on_error=(not arguments.stop_on_error),
            progress_callback=(create_progress_callback(logger)),
        )

    except (
        FileNotFoundError,
        JQuantsCalendarError,
        JQuantsDownloadError,
        ValueError,
        WatchlistError,
    ) as error:
        logger.error(
            "J-Quants履歴取込を実行できません: %s",
            error,
        )
        return

    log_result(
        logger=logger,
        result=result,
    )

    repository = MarketBarRepository(settings.database_path)

    logger.info(
        "SQLite内5分足総数: %d",
        repository.count(interval_minutes=INTERVAL_MINUTES),
    )

    if result.failed_request_count > 0:
        logger.warning(
            "一部の履歴取得に失敗しました。"
            "同じコマンドを再実行すると、"
            "UPSERTにより既存データを重複させず"
            "再取得できます。"
        )


if __name__ == "__main__":
    main()
