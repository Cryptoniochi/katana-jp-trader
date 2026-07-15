"""Watch List銘柄のJ-Quants履歴分足をSQLiteへ保存する。"""

import argparse
import csv
import logging
import os
from collections.abc import Callable
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
from app.market.history_retry import (
    RetryExhaustedError,
    RetryPolicy,
)
from app.market.history_state import (
    HistoryStateError,
    HistoryStateRepository,
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
from app.watchlist import (
    WatchlistError,
    load_watchlist,
)

DEFAULT_START_DATE = "2026-01-01"
DEFAULT_END_DATE = "2026-07-15"
DEFAULT_CHUNK_BUSINESS_DAYS = 20
DEFAULT_REQUEST_INTERVAL_SECONDS = 1.1

DEFAULT_RETRY_MAX_ATTEMPTS = 3
DEFAULT_RETRY_INITIAL_DELAY_SECONDS = 2.0
DEFAULT_RETRY_BACKOFF_MULTIPLIER = 2.0
DEFAULT_RETRY_MAXIMUM_DELAY_SECONDS = 30.0

DEFAULT_STATE_FILE = Path(
    "data/state/jquants_history_import_state.json"
)
DEFAULT_REPORT_FILE = Path(
    "data/reports/jquants_history_import_report.csv"
)

INTERVAL_MINUTES = 5
DATA_SOURCE = "jquants"

CSV_FIELD_NAMES = [
    "record_type",
    "code",
    "start_date",
    "end_date",
    "business_date_count",
    "chunk_count",
    "request_count",
    "successful_request_count",
    "empty_request_count",
    "failed_request_count",
    "minute_bar_count",
    "five_minute_bar_count",
    "processed_bar_count",
    "message",
]

ProgressCallback = Callable[
    [HistoryImportProgress],
    None,
]


def parse_arguments(
    arguments: list[str] | None = None,
) -> argparse.Namespace:
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
        help=(
            "Watch Listのパス。"
            f"既定値: {settings.watchlist_path}"
        ),
    )

    parser.add_argument(
        "--codes",
        nargs="+",
        default=None,
        help=(
            "直接指定する銘柄コード。"
            "指定時はWatch Listより優先します。"
        ),
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
        help=(
            "進捗管理上の1チャンク当たり営業日数。"
            f"既定値: {DEFAULT_CHUNK_BUSINESS_DAYS}"
        ),
    )

    parser.add_argument(
        "--request-interval",
        type=float,
        default=DEFAULT_REQUEST_INTERVAL_SECONDS,
        help=(
            "分足APIリクエスト間の待機秒数。"
            f"既定値: {DEFAULT_REQUEST_INTERVAL_SECONDS}"
        ),
    )

    parser.add_argument(
        "--state-file",
        type=Path,
        default=DEFAULT_STATE_FILE,
        help=(
            "途中再開状態を保存するJSONファイル。"
            f"既定値: {DEFAULT_STATE_FILE}"
        ),
    )

    parser.add_argument(
        "--reset-state",
        action="store_true",
        help=(
            "履歴取込開始前に保存済みの"
            "途中再開状態を削除します。"
        ),
    )

    parser.add_argument(
        "--report-csv",
        type=Path,
        default=DEFAULT_REPORT_FILE,
        help=(
            "取込結果を保存するCSVファイル。"
            f"既定値: {DEFAULT_REPORT_FILE}"
        ),
    )

    parser.add_argument(
        "--no-report",
        action="store_true",
        help="CSVレポートを出力しません。",
    )

    parser.add_argument(
        "--retry-max-attempts",
        type=int,
        default=DEFAULT_RETRY_MAX_ATTEMPTS,
        help=(
            "一時エラー発生時の最大試行回数。"
            f"既定値: {DEFAULT_RETRY_MAX_ATTEMPTS}"
        ),
    )

    parser.add_argument(
        "--retry-initial-delay",
        type=float,
        default=DEFAULT_RETRY_INITIAL_DELAY_SECONDS,
        help=(
            "最初の再試行までの待機秒数。"
            f"既定値: {DEFAULT_RETRY_INITIAL_DELAY_SECONDS}"
        ),
    )

    parser.add_argument(
        "--retry-backoff",
        type=float,
        default=DEFAULT_RETRY_BACKOFF_MULTIPLIER,
        help=(
            "再試行待機時間の倍率。"
            f"既定値: {DEFAULT_RETRY_BACKOFF_MULTIPLIER}"
        ),
    )

    parser.add_argument(
        "--retry-max-delay",
        type=float,
        default=DEFAULT_RETRY_MAXIMUM_DELAY_SECONDS,
        help=(
            "再試行待機時間の上限秒数。"
            f"既定値: {DEFAULT_RETRY_MAXIMUM_DELAY_SECONDS}"
        ),
    )

    parser.add_argument(
        "--stop-on-error",
        action="store_true",
        help="取得失敗が発生した時点で履歴取込を停止します。",
    )

    return parser.parse_args(arguments)


def parse_date(
    value: str,
) -> date:
    """YYYY-MM-DD形式の日付をdateへ変換する。"""

    try:
        return datetime.strptime(
            value,
            "%Y-%m-%d",
        ).date()

    except ValueError as error:
        raise ValueError(
            "日付はYYYY-MM-DD形式で指定してください。"
        ) from error


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
) -> ProgressCallback:
    """進捗をログへ出力するコールバックを返す。"""

    def show_progress(
        progress: HistoryImportProgress,
    ) -> None:
        logger.info(
            "%s",
            format_progress_message(progress),
        )

    return show_progress


def create_retry_policy(
    *,
    max_attempts: int,
    initial_delay_seconds: float,
    backoff_multiplier: float,
    maximum_delay_seconds: float,
) -> RetryPolicy:
    """CLI指定値から再試行条件を作成する。"""

    return RetryPolicy(
        max_attempts=max_attempts,
        initial_delay_seconds=initial_delay_seconds,
        backoff_multiplier=backoff_multiplier,
        maximum_delay_seconds=maximum_delay_seconds,
    )


def run_history_import(
    *,
    codes: list[str],
    start_date: date,
    end_date: date,
    chunk_business_days: int,
    request_interval_seconds: float,
    continue_on_error: bool,
    state_file_path: Path | None = None,
    retry_policy: RetryPolicy | None = None,
    calendar_reader: TradingCalendarReader | None = None,
    batch_importer: HistoricalBatchImporter | None = None,
    state_repository: HistoryStateRepository | None = None,
    retry_sleeper: Callable[[float], None] | None = None,
    progress_callback: ProgressCallback | None = None,
) -> HistoryImportResult:
    """履歴取込を構成して実行する。"""

    if request_interval_seconds < 0:
        raise ValueError(
            "リクエスト間隔は0秒以上で指定してください。"
        )

    resolved_calendar_reader = calendar_reader

    if resolved_calendar_reader is None:
        resolved_calendar_reader = (
            JQuantsTradingCalendarClient()
        )

    resolved_batch_importer = batch_importer

    if resolved_batch_importer is None:
        market_bar_repository = MarketBarRepository(
            settings.database_path
        )

        resolved_batch_importer = JQuantsBatchImportService(
            downloader=JQuantsMinuteDownloader(),
            aggregator=StockPriceAggregator(),
            repository=market_bar_repository,
            request_interval_seconds=(
                request_interval_seconds
            ),
        )

    resolved_state_repository = state_repository

    if (
        resolved_state_repository is None
        and state_file_path is not None
    ):
        resolved_state_repository = HistoryStateRepository(
            state_file_path
        )

    importer_arguments: dict[str, object] = {
        "calendar_reader": resolved_calendar_reader,
        "batch_importer": resolved_batch_importer,
        "state_repository": resolved_state_repository,
        "retry_policy": retry_policy or RetryPolicy(),
    }

    if retry_sleeper is not None:
        importer_arguments["retry_sleeper"] = retry_sleeper

    importer = JQuantsHistoryImporter(
        **importer_arguments,
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


def create_csv_rows(
    result: HistoryImportResult,
) -> list[dict[str, str | int]]:
    """履歴取込結果をCSV行へ変換する。"""

    rows: list[dict[str, str | int]] = [
        {
            "record_type": "summary",
            "code": "",
            "start_date": result.start_date.isoformat(),
            "end_date": result.end_date.isoformat(),
            "business_date_count": result.business_date_count,
            "chunk_count": result.chunk_count,
            "request_count": result.request_count,
            "successful_request_count": (
                result.successful_request_count
            ),
            "empty_request_count": (
                result.empty_request_count
            ),
            "failed_request_count": (
                result.failed_request_count
            ),
            "minute_bar_count": result.minute_bar_count,
            "five_minute_bar_count": (
                result.five_minute_bar_count
            ),
            "processed_bar_count": (
                result.processed_bar_count
            ),
            "message": (
                f"code_count={result.code_count};"
                f"successful_code_count="
                f"{result.successful_code_count};"
                f"failed_code_count="
                f"{result.failed_code_count}"
            ),
        }
    ]

    for symbol_result in result.code_results:
        rows.append(
            {
                "record_type": "symbol",
                "code": symbol_result.code,
                "start_date": (
                    result.start_date.isoformat()
                ),
                "end_date": result.end_date.isoformat(),
                "business_date_count": (
                    symbol_result.business_date_count
                ),
                "chunk_count": symbol_result.chunk_count,
                "request_count": (
                    symbol_result.request_count
                ),
                "successful_request_count": (
                    symbol_result.successful_request_count
                ),
                "empty_request_count": (
                    symbol_result.empty_request_count
                ),
                "failed_request_count": (
                    symbol_result.failed_request_count
                ),
                "minute_bar_count": (
                    symbol_result.minute_bar_count
                ),
                "five_minute_bar_count": (
                    symbol_result.five_minute_bar_count
                ),
                "processed_bar_count": (
                    symbol_result.processed_bar_count
                ),
                "message": "",
            }
        )

    for failure in result.failures:
        rows.append(
            {
                "record_type": "failure",
                "code": failure.code,
                "start_date": (
                    failure.start_date.isoformat()
                ),
                "end_date": failure.end_date.isoformat(),
                "business_date_count": "",
                "chunk_count": "",
                "request_count": "",
                "successful_request_count": "",
                "empty_request_count": "",
                "failed_request_count": 1,
                "minute_bar_count": "",
                "five_minute_bar_count": "",
                "processed_bar_count": "",
                "message": failure.message,
            }
        )

    return rows


def write_csv_report(
    result: HistoryImportResult,
    output_path: Path,
) -> Path:
    """履歴取込結果をCSVへ安全に保存する。"""

    if output_path.exists() and not output_path.is_file():
        raise OSError(
            "CSVレポートの出力先が"
            f"ファイルではありません。 path={output_path}"
        )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary_path = output_path.with_suffix(
        f"{output_path.suffix}.tmp"
    )

    rows = create_csv_rows(result)

    try:
        with temporary_path.open(
            mode="w",
            encoding="utf-8-sig",
            newline="",
        ) as csv_file:
            writer = csv.DictWriter(
                csv_file,
                fieldnames=CSV_FIELD_NAMES,
                extrasaction="raise",
            )

            writer.writeheader()
            writer.writerows(rows)

            csv_file.flush()
            os.fsync(csv_file.fileno())

        os.replace(
            temporary_path,
            output_path,
        )

    except (
        OSError,
        csv.Error,
        ValueError,
    ) as error:
        try:
            temporary_path.unlink(
                missing_ok=True
            )
        except OSError:
            pass

        raise OSError(
            "CSVレポートを保存できませんでした。"
            f" path={output_path}"
        ) from error

    return output_path


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
        "履歴取込リクエスト: "
        "requests=%d successful=%d empty=%d failed=%d",
        result.request_count,
        result.successful_request_count,
        result.empty_request_count,
        result.failed_request_count,
    )

    logger.info(
        "履歴取込データ: "
        "minute_bars=%d five_minute_bars=%d "
        "processed=%d",
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
            "履歴取得失敗: "
            "code=%s start=%s end=%s reason=%s",
            failure.code,
            failure.start_date,
            failure.end_date,
            failure.message,
        )

    if len(result.failures) > 20:
        logger.warning(
            "履歴取得失敗の残り%d件は"
            "ログ表示を省略しました。",
            len(result.failures) - 20,
        )


def main() -> None:
    """Watch List銘柄の履歴データを取り込む。"""

    arguments = parse_arguments()

    print("=" * 50)
    print(
        f"{settings.app_name} "
        "- J-Quants Historical Import"
    )
    print(f"Version : {settings.version}")
    print("=" * 50)

    settings.create_directories()
    initialize_database(
        settings.database_path
    )

    logger = create_logger(
        settings.logs_dir
    )

    try:
        codes, code_source = resolve_codes(
            command_codes=arguments.codes,
            watchlist_path=arguments.watchlist,
        )

        start_date = parse_date(
            arguments.start_date
        )
        end_date = parse_date(
            arguments.end_date
        )

        retry_policy = create_retry_policy(
            max_attempts=(
                arguments.retry_max_attempts
            ),
            initial_delay_seconds=(
                arguments.retry_initial_delay
            ),
            backoff_multiplier=(
                arguments.retry_backoff
            ),
            maximum_delay_seconds=(
                arguments.retry_max_delay
            ),
        )

        state_repository = HistoryStateRepository(
            arguments.state_file
        )

        if arguments.reset_state:
            state_repository.reset()

            logger.info(
                "履歴取込状態をリセットしました。 "
                "path=%s",
                arguments.state_file,
            )

        logger.info(
            "履歴取込対象を読み込みました。 "
            "source=%s codes=%d "
            "start=%s end=%s "
            "chunk_business_days=%d "
            "request_interval=%.2f "
            "state_file=%s "
            "retry_max_attempts=%d "
            "retry_initial_delay=%.2f "
            "retry_backoff=%.2f "
            "retry_max_delay=%.2f",
            code_source,
            len(codes),
            start_date,
            end_date,
            arguments.chunk_business_days,
            arguments.request_interval,
            arguments.state_file,
            retry_policy.max_attempts,
            retry_policy.initial_delay_seconds,
            retry_policy.backoff_multiplier,
            retry_policy.maximum_delay_seconds,
        )

        result = run_history_import(
            codes=codes,
            start_date=start_date,
            end_date=end_date,
            chunk_business_days=(
                arguments.chunk_business_days
            ),
            request_interval_seconds=(
                arguments.request_interval
            ),
            continue_on_error=(
                not arguments.stop_on_error
            ),
            state_repository=state_repository,
            retry_policy=retry_policy,
            progress_callback=(
                create_progress_callback(logger)
            ),
        )

        log_result(
            logger=logger,
            result=result,
        )

        if not arguments.no_report:
            report_path = write_csv_report(
                result=result,
                output_path=arguments.report_csv,
            )

            logger.info(
                "履歴取込CSVレポートを保存しました。 "
                "path=%s",
                report_path,
            )

        market_bar_repository = MarketBarRepository(
            settings.database_path
        )

        logger.info(
            "SQLite内5分足総数: %d",
            market_bar_repository.count(
                interval_minutes=INTERVAL_MINUTES
            ),
        )

        if result.failed_request_count > 0:
            logger.warning(
                "一部の履歴取得に失敗しました。"
                "同じ状態ファイルを指定して再実行すると、"
                "完了済みチャンクをスキップし、"
                "未完了チャンクから再開します。"
            )

    except (
        FileNotFoundError,
        HistoryStateError,
        JQuantsCalendarError,
        JQuantsDownloadError,
        OSError,
        RetryExhaustedError,
        ValueError,
        WatchlistError,
    ) as error:
        logger.error(
            "J-Quants履歴取込を実行できません: %s",
            error,
        )


if __name__ == "__main__":
    main()