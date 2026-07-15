"""J-Quants履歴分足を差分更新する定期実行CLI。"""

import argparse
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from app.database import initialize_database
from app.import_jquants_history import (
    DEFAULT_CHUNK_BUSINESS_DAYS,
    DEFAULT_REQUEST_INTERVAL_SECONDS,
    DEFAULT_RETRY_BACKOFF_MULTIPLIER,
    DEFAULT_RETRY_INITIAL_DELAY_SECONDS,
    DEFAULT_RETRY_MAX_ATTEMPTS,
    DEFAULT_RETRY_MAXIMUM_DELAY_SECONDS,
    INTERVAL_MINUTES,
    create_progress_callback,
    create_retry_policy,
    parse_date,
    resolve_codes,
    run_history_import,
    write_csv_report,
)
from app.logger import create_logger
from app.market.bar_repository import MarketBarRepository
from app.market.history_progress import (
    HistoryImportFailure,
    HistoryImportProgress,
    HistoryImportResult,
    HistorySymbolResult,
)
from app.market.history_retry import (
    RetryExhaustedError,
    RetryPolicy,
)
from app.market.history_state import (
    HistoryStateError,
    HistoryStateRepository,
)
from app.market.incremental_update import (
    IncrementalUpdatePlan,
    IncrementalUpdatePlanner,
)
from app.market.jquants_calendar import (
    JQuantsCalendarError,
    JQuantsTradingCalendarClient,
)
from app.market.jquants_downloader import (
    JQuantsDownloadError,
)
from app.market.jquants_history_importer import (
    HistoricalBatchImporter,
    TradingCalendarReader,
)
from app.market.process_lock import (
    AlreadyLockedError,
    ProcessLock,
    ProcessLockError,
)
from app.settings import settings
from app.watchlist import WatchlistError


EXIT_SUCCESS = 0
EXIT_PARTIAL_FAILURE = 1
EXIT_ALREADY_RUNNING = 2
EXIT_EXECUTION_ERROR = 3

DEFAULT_INITIAL_START_DATE = "2026-01-01"
DEFAULT_LOCK_STALE_SECONDS = 60 * 60

DEFAULT_STATE_FILE = (
    settings.data_dir
    / "state"
    / "jquants_incremental_update.json"
)

DEFAULT_REPORT_FILE = (
    settings.reports_dir
    / "jquants_incremental_update.csv"
)

DEFAULT_LOCK_FILE = (
    settings.data_dir
    / "locks"
    / "jquants_incremental_update.lock"
)

ProgressCallback = Callable[
    [HistoryImportProgress],
    None,
]


@dataclass(frozen=True, slots=True)
class ScheduledUpdateResult:
    """1回の定期差分更新結果。"""

    plan: IncrementalUpdatePlan
    history_result: HistoryImportResult
    report_path: Path | None

    @property
    def updated_code_count(self) -> int:
        """更新対象だった銘柄数を返す。"""

        return self.plan.update_code_count

    @property
    def skipped_code_count(self) -> int:
        """更新不要だった銘柄数を返す。"""

        return self.plan.skipped_code_count

    @property
    def failed_request_count(self) -> int:
        """失敗したAPIリクエスト数を返す。"""

        return self.history_result.failed_request_count

    @property
    def is_successful(self) -> bool:
        """取得失敗がなかったか返す。"""

        return self.failed_request_count == 0


def parse_arguments(
    arguments: list[str] | None = None,
) -> argparse.Namespace:
    """定期差分更新CLIの引数を読み込む。"""

    parser = argparse.ArgumentParser(
        description=(
            "SQLiteに保存済みの最新時間足を確認し、"
            "J-Quants履歴分足の未取得期間だけを更新します。"
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
        "--initial-start-date",
        default=DEFAULT_INITIAL_START_DATE,
        help=(
            "保存データがない銘柄の初回取得開始日。"
            "形式: YYYY-MM-DD"
        ),
    )

    parser.add_argument(
        "--target-end-date",
        default=None,
        help=(
            "差分更新の終了日。"
            "省略時は実行日。"
            "形式: YYYY-MM-DD"
        ),
    )

    parser.add_argument(
        "--chunk-business-days",
        type=int,
        default=DEFAULT_CHUNK_BUSINESS_DAYS,
        help=(
            "履歴取込の1チャンク当たり営業日数。"
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
        help="実行前に途中再開状態を削除します。",
    )

    parser.add_argument(
        "--report-csv",
        type=Path,
        default=DEFAULT_REPORT_FILE,
        help=(
            "実行結果を保存するCSVファイル。"
            f"既定値: {DEFAULT_REPORT_FILE}"
        ),
    )

    parser.add_argument(
        "--no-report",
        action="store_true",
        help="CSVレポートを出力しません。",
    )

    parser.add_argument(
        "--lock-file",
        type=Path,
        default=DEFAULT_LOCK_FILE,
        help=(
            "多重起動防止用ロックファイル。"
            f"既定値: {DEFAULT_LOCK_FILE}"
        ),
    )

    parser.add_argument(
        "--lock-stale-seconds",
        type=float,
        default=DEFAULT_LOCK_STALE_SECONDS,
        help=(
            "異常終了ロックを期限切れとみなす秒数。"
            f"既定値: {DEFAULT_LOCK_STALE_SECONDS}"
        ),
    )

    parser.add_argument(
        "--retry-max-attempts",
        type=int,
        default=DEFAULT_RETRY_MAX_ATTEMPTS,
        help=(
            "一時エラー時の最大試行回数。"
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
        help="取得失敗が発生した時点で処理を停止します。",
    )

    return parser.parse_args(arguments)


def resolve_target_end_date(
    value: str | None,
    *,
    today: date | None = None,
) -> date:
    """CLI指定値または実行日から更新終了日を決定する。"""

    if value is not None:
        return parse_date(value)

    return today or date.today()


def merge_history_results(
    *,
    plan: IncrementalUpdatePlan,
    imported_results: Sequence[HistoryImportResult],
) -> HistoryImportResult:
    """銘柄ごとの取込結果を1つの実行結果へ統合する。"""

    symbol_results_by_code: dict[
        str,
        HistorySymbolResult,
    ] = {}

    failures: list[HistoryImportFailure] = []

    for imported_result in imported_results:
        failures.extend(imported_result.failures)

        for symbol_result in imported_result.code_results:
            if symbol_result.code in symbol_results_by_code:
                raise ValueError(
                    "同一銘柄の履歴取込結果が"
                    "複数回登録されています。 "
                    f"code={symbol_result.code}"
                )

            symbol_results_by_code[
                symbol_result.code
            ] = symbol_result

    ordered_symbol_results: list[
        HistorySymbolResult
    ] = []

    for task in plan.tasks:
        symbol_result = symbol_results_by_code.get(
            task.code
        )

        if symbol_result is None:
            symbol_result = HistorySymbolResult(
                code=task.code,
                business_date_count=0,
                chunk_count=0,
                request_count=0,
                successful_request_count=0,
                empty_request_count=0,
                failed_request_count=0,
                minute_bar_count=0,
                five_minute_bar_count=0,
                processed_bar_count=0,
            )

        ordered_symbol_results.append(
            symbol_result
        )

    return HistoryImportResult(
        start_date=plan.initial_start_date,
        end_date=plan.target_end_date,
        code_results=ordered_symbol_results,
        failures=failures,
    )


def run_incremental_update(
    *,
    codes: Sequence[str],
    initial_start_date: date,
    target_end_date: date,
    chunk_business_days: int,
    request_interval_seconds: float,
    continue_on_error: bool,
    repository: MarketBarRepository,
    calendar_reader: TradingCalendarReader,
    state_repository: HistoryStateRepository | None = None,
    retry_policy: RetryPolicy | None = None,
    batch_importer: HistoricalBatchImporter | None = None,
    retry_sleeper: Callable[[float], None] | None = None,
    progress_callback: ProgressCallback | None = None,
    report_path: Path | None = None,
    today: date | None = None,
) -> ScheduledUpdateResult:
    """差分計画を作成し、必要な銘柄だけ履歴取込する。"""

    planner = IncrementalUpdatePlanner(
        repository=repository,
        calendar_reader=calendar_reader,
    )

    plan = planner.create_plan(
        codes=codes,
        initial_start_date=initial_start_date,
        target_end_date=target_end_date,
        interval_minutes=INTERVAL_MINUTES,
        today=today,
    )

    imported_results: list[
        HistoryImportResult
    ] = []

    for task in plan.update_tasks:
        update_start_date = (
            task.update_start_date
        )
        update_end_date = (
            task.update_end_date
        )

        if (
            update_start_date is None
            or update_end_date is None
        ):
            raise RuntimeError(
                "更新対象タスクに有効な期間がありません。 "
                f"code={task.code}"
            )

        imported_result = run_history_import(
            codes=[task.code],
            start_date=update_start_date,
            end_date=update_end_date,
            chunk_business_days=(
                chunk_business_days
            ),
            request_interval_seconds=(
                request_interval_seconds
            ),
            continue_on_error=continue_on_error,
            retry_policy=retry_policy,
            calendar_reader=calendar_reader,
            batch_importer=batch_importer,
            state_repository=state_repository,
            retry_sleeper=retry_sleeper,
            progress_callback=progress_callback,
        )

        imported_results.append(
            imported_result
        )

    history_result = merge_history_results(
        plan=plan,
        imported_results=imported_results,
    )

    saved_report_path: Path | None = None

    if report_path is not None:
        saved_report_path = write_csv_report(
            result=history_result,
            output_path=report_path,
        )

    return ScheduledUpdateResult(
        plan=plan,
        history_result=history_result,
        report_path=saved_report_path,
    )


def run_locked_incremental_update(
    *,
    process_lock: ProcessLock,
    codes: Sequence[str],
    initial_start_date: date,
    target_end_date: date,
    chunk_business_days: int,
    request_interval_seconds: float,
    continue_on_error: bool,
    repository: MarketBarRepository,
    calendar_reader: TradingCalendarReader,
    state_repository: HistoryStateRepository | None = None,
    retry_policy: RetryPolicy | None = None,
    batch_importer: HistoricalBatchImporter | None = None,
    retry_sleeper: Callable[[float], None] | None = None,
    progress_callback: ProgressCallback | None = None,
    report_path: Path | None = None,
    today: date | None = None,
) -> ScheduledUpdateResult:
    """プロセスロックを取得して差分更新を実行する。"""

    with process_lock:
        return run_incremental_update(
            codes=codes,
            initial_start_date=initial_start_date,
            target_end_date=target_end_date,
            chunk_business_days=(
                chunk_business_days
            ),
            request_interval_seconds=(
                request_interval_seconds
            ),
            continue_on_error=continue_on_error,
            repository=repository,
            calendar_reader=calendar_reader,
            state_repository=state_repository,
            retry_policy=retry_policy,
            batch_importer=batch_importer,
            retry_sleeper=retry_sleeper,
            progress_callback=progress_callback,
            report_path=report_path,
            today=today,
        )


def determine_exit_code(
    result: ScheduledUpdateResult,
) -> int:
    """定期差分更新結果から終了コードを決定する。"""

    if result.failed_request_count > 0:
        return EXIT_PARTIAL_FAILURE

    return EXIT_SUCCESS


def log_update_result(
    logger: logging.Logger,
    result: ScheduledUpdateResult,
) -> None:
    """定期差分更新結果をログへ出力する。"""

    logger.info(
        "J-Quants差分更新完了: "
        "codes=%d update_codes=%d skipped_codes=%d "
        "business_dates=%d requests=%d "
        "successful=%d empty=%d failed=%d "
        "processed=%d",
        result.plan.code_count,
        result.updated_code_count,
        result.skipped_code_count,
        result.plan.total_business_date_count,
        result.history_result.request_count,
        result.history_result.successful_request_count,
        result.history_result.empty_request_count,
        result.history_result.failed_request_count,
        result.history_result.processed_bar_count,
    )

    for task in result.plan.tasks:
        logger.info(
            "J-Quants差分更新計画: "
            "code=%s action=%s "
            "latest_saved_at=%s "
            "requested_start=%s requested_end=%s "
            "business_dates=%d",
            task.code,
            task.action.value,
            task.latest_saved_at,
            task.requested_start_date,
            task.requested_end_date,
            task.business_date_count,
        )

    if result.report_path is not None:
        logger.info(
            "J-Quants差分更新CSVレポート: path=%s",
            result.report_path,
        )


def main(
    arguments: list[str] | None = None,
) -> int:
    """J-Quants履歴分足の定期差分更新を実行する。"""

    parsed_arguments = parse_arguments(
        arguments
    )

    print("=" * 50)
    print(
        f"{settings.app_name} "
        "- J-Quants Incremental Update"
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
            command_codes=(
                parsed_arguments.codes
            ),
            watchlist_path=(
                parsed_arguments.watchlist
            ),
        )

        initial_start_date = parse_date(
            parsed_arguments.initial_start_date
        )

        target_end_date = (
            resolve_target_end_date(
                parsed_arguments.target_end_date
            )
        )

        retry_policy = create_retry_policy(
            max_attempts=(
                parsed_arguments.retry_max_attempts
            ),
            initial_delay_seconds=(
                parsed_arguments.retry_initial_delay
            ),
            backoff_multiplier=(
                parsed_arguments.retry_backoff
            ),
            maximum_delay_seconds=(
                parsed_arguments.retry_max_delay
            ),
        )

        state_repository = (
            HistoryStateRepository(
                parsed_arguments.state_file
            )
        )

        if parsed_arguments.reset_state:
            state_repository.reset()

            logger.info(
                "差分更新状態をリセットしました。 "
                "path=%s",
                parsed_arguments.state_file,
            )

        repository = MarketBarRepository(
            settings.database_path
        )

        calendar_reader = (
            JQuantsTradingCalendarClient()
        )

        process_lock = ProcessLock(
            file_path=parsed_arguments.lock_file,
            process_name=(
                "jquants-incremental-update"
            ),
            stale_after_seconds=(
                parsed_arguments.lock_stale_seconds
            ),
        )

        report_path = (
            None
            if parsed_arguments.no_report
            else parsed_arguments.report_csv
        )

        logger.info(
            "J-Quants差分更新開始: "
            "source=%s codes=%d "
            "initial_start=%s target_end=%s "
            "chunk_business_days=%d "
            "request_interval=%.2f "
            "state_file=%s lock_file=%s",
            code_source,
            len(codes),
            initial_start_date,
            target_end_date,
            parsed_arguments.chunk_business_days,
            parsed_arguments.request_interval,
            parsed_arguments.state_file,
            parsed_arguments.lock_file,
        )

        result = run_locked_incremental_update(
            process_lock=process_lock,
            codes=codes,
            initial_start_date=initial_start_date,
            target_end_date=target_end_date,
            chunk_business_days=(
                parsed_arguments.chunk_business_days
            ),
            request_interval_seconds=(
                parsed_arguments.request_interval
            ),
            continue_on_error=(
                not parsed_arguments.stop_on_error
            ),
            repository=repository,
            calendar_reader=calendar_reader,
            state_repository=state_repository,
            retry_policy=retry_policy,
            progress_callback=(
                create_progress_callback(logger)
            ),
            report_path=report_path,
        )

        log_update_result(
            logger=logger,
            result=result,
        )

        return determine_exit_code(
            result
        )

    except AlreadyLockedError as error:
        logger.warning(
            "J-Quants差分更新を開始しませんでした。 "
            "既に別プロセスが実行中です: %s",
            error,
        )

        return EXIT_ALREADY_RUNNING

    except (
        FileNotFoundError,
        HistoryStateError,
        JQuantsCalendarError,
        JQuantsDownloadError,
        OSError,
        ProcessLockError,
        RetryExhaustedError,
        ValueError,
        WatchlistError,
    ) as error:
        logger.error(
            "J-Quants差分更新を実行できません: %s",
            error,
        )

        return EXIT_EXECUTION_ERROR


if __name__ == "__main__":
    raise SystemExit(main())