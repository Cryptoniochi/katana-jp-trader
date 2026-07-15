"""J-Quantsの履歴分足を期間分割して取り込む処理。"""

from collections.abc import Callable
from datetime import date
import logging
from typing import Protocol

from app.market.date_range import (
    filter_date_range,
    split_dates,
)
from app.market.history_progress import (
    HistoryImportFailure,
    HistoryImportProgress,
    HistoryImportResult,
    HistorySymbolResult,
)
from app.market.history_retry import (
    RetryAttempt,
    RetryExhaustedError,
    RetryPolicy,
    run_with_retry,
)
from app.market.history_state import (
    HistoryImportState,
    HistoryStateRepository,
    HistoryTaskKey,
)
from app.market.jquants_batch_import import (
    JQuantsBatchImportResult,
)

LOGGER = logging.getLogger(__name__)


class TradingCalendarReader(Protocol):
    """取引カレンダー取得処理のインターフェース。"""

    def get_business_dates(
        self,
        start_date: date,
        end_date: date,
    ) -> list[date]:
        """指定期間の営業日一覧を返す。"""


class HistoricalBatchImporter(Protocol):
    """営業日を指定できる一括取込処理。"""

    def run_dates(
        self,
        codes: list[str],
        target_dates: list[date],
        *,
        interval_minutes: int = 5,
        data_source: str = "jquants",
        continue_on_error: bool = True,
        progress_callback: object | None = None,
    ) -> JQuantsBatchImportResult:
        """指定銘柄・日付の市場データを取り込む。"""


HistoryProgressCallback = Callable[
    [HistoryImportProgress],
    None,
]


class JQuantsHistoryImporter:
    """J-Quantsの履歴分足を分割してSQLiteへ取り込む。"""

    def __init__(
        self,
        calendar_reader: TradingCalendarReader,
        batch_importer: HistoricalBatchImporter,
        *,
        state_repository: HistoryStateRepository | None = None,
        retry_policy: RetryPolicy | None = None,
        retry_exceptions: tuple[type[Exception], ...] = (
            TimeoutError,
            ConnectionError,
            OSError,
        ),
        retry_sleeper: Callable[[float], None] | None = None,
    ) -> None:
        """履歴取込に必要な依存処理を設定する。

        Args:
            calendar_reader:
                営業日を取得する処理。
            batch_importer:
                指定銘柄・指定営業日のデータを取り込む処理。
            state_repository:
                チャンクの完了・失敗状態を保存するリポジトリ。
                指定しない場合は状態を永続化しない。
            retry_policy:
                一時的な失敗に対する再試行条件。
            retry_exceptions:
                再試行対象とする例外型。
            retry_sleeper:
                再試行前の待機処理。
                テストでは待機しない関数へ差し替えられる。
        """

        if not retry_exceptions:
            raise ValueError(
                "再試行対象の例外を1件以上指定してください。"
            )

        self.calendar_reader = calendar_reader
        self.batch_importer = batch_importer
        self.state_repository = state_repository
        self.retry_policy = retry_policy or RetryPolicy()
        self.retry_exceptions = retry_exceptions
        self.retry_sleeper = retry_sleeper

    def run(
        self,
        codes: list[str],
        start_date: date,
        end_date: date,
        *,
        chunk_business_days: int = 20,
        interval_minutes: int = 5,
        data_source: str = "jquants",
        continue_on_error: bool = True,
        progress_callback: HistoryProgressCallback | None = None,
    ) -> HistoryImportResult:
        """複数銘柄の履歴データを期間分割して取り込む。

        状態リポジトリが指定されている場合は、実行開始時に保存済み
        状態を読み込む。完了済みの銘柄・チャンクは再取得せず、
        未完了または失敗したチャンクだけを実行する。

        チャンクの成功または失敗が確定するたびに状態を保存する。
        状態保存に失敗した場合は、二重取込を防ぐため処理を停止する。
        """

        normalized_codes = self._normalize_codes(codes)

        self._validate_run_arguments(
            start_date=start_date,
            end_date=end_date,
            chunk_business_days=chunk_business_days,
            interval_minutes=interval_minutes,
            data_source=data_source,
        )

        business_dates = self.calendar_reader.get_business_dates(
            start_date=start_date,
            end_date=end_date,
        )

        business_dates = filter_date_range(
            target_dates=business_dates,
            start_date=start_date,
            end_date=end_date,
        )

        date_chunks = split_dates(
            target_dates=business_dates,
            chunk_size=chunk_business_days,
        )

        state = self._load_state()

        total_tasks = len(normalized_codes) * len(date_chunks)
        completed_tasks = 0

        symbol_results: list[HistorySymbolResult] = []
        failures: list[HistoryImportFailure] = []

        for code in normalized_codes:
            symbol_request_count = 0
            symbol_successful_count = 0
            symbol_empty_count = 0
            symbol_failed_count = 0

            symbol_minute_bar_count = 0
            symbol_five_minute_bar_count = 0
            symbol_processed_bar_count = 0

            for chunk_number, target_dates in enumerate(
                date_chunks,
                start=1,
            ):
                chunk_start = target_dates[0]
                chunk_end = target_dates[-1]

                task_key = HistoryTaskKey(
                    code=code,
                    start_date=chunk_start,
                    end_date=chunk_end,
                )

                if state.is_completed(task_key):
                    LOGGER.info(
                        "履歴取込の完了済みチャンクをスキップします。 "
                        "code=%s start_date=%s end_date=%s",
                        code,
                        chunk_start.isoformat(),
                        chunk_end.isoformat(),
                    )

                    completed_tasks += 1

                    self._notify_progress(
                        progress_callback=progress_callback,
                        completed_tasks=completed_tasks,
                        total_tasks=total_tasks,
                        code=code,
                        chunk_number=chunk_number,
                        chunk_count=len(date_chunks),
                        start_date=chunk_start,
                        end_date=chunk_end,
                        batch_result=self._create_skipped_batch_result(
                            date_count=len(target_dates),
                        ),
                    )

                    continue

                try:
                    batch_result = self._run_chunk_with_retry(
                        code=code,
                        target_dates=target_dates,
                        interval_minutes=interval_minutes,
                        data_source=data_source,
                        continue_on_error=continue_on_error,
                    )

                except RetryExhaustedError as error:
                    attempt_count = max(
                        len(error.attempts),
                        1,
                    )
                    message = self._retry_error_message(error)

                    state = state.mark_failed(
                        task_key,
                        message=message,
                        attempt_count=attempt_count,
                    )
                    self._save_state(state)

                    LOGGER.error(
                        "履歴取込チャンクの再試行が上限に達しました。 "
                        "code=%s start_date=%s end_date=%s "
                        "attempt_count=%s error=%s",
                        code,
                        chunk_start.isoformat(),
                        chunk_end.isoformat(),
                        attempt_count,
                        message,
                    )

                    if not continue_on_error:
                        raise

                    batch_result = self._create_failed_batch_result(
                        date_count=len(target_dates),
                        failed_count=len(target_dates),
                    )

                    failures.append(
                        HistoryImportFailure(
                            code=code,
                            start_date=chunk_start,
                            end_date=chunk_end,
                            message=message,
                        )
                    )

                except Exception as error:
                    message = str(error)

                    state = state.mark_failed(
                        task_key,
                        message=message,
                        attempt_count=1,
                    )
                    self._save_state(state)

                    LOGGER.exception(
                        "履歴取込チャンクで再試行対象外の例外が発生しました。 "
                        "code=%s start_date=%s end_date=%s",
                        code,
                        chunk_start.isoformat(),
                        chunk_end.isoformat(),
                    )

                    if not continue_on_error:
                        raise

                    batch_result = self._create_failed_batch_result(
                        date_count=len(target_dates),
                        failed_count=len(target_dates),
                    )

                    failures.append(
                        HistoryImportFailure(
                            code=code,
                            start_date=chunk_start,
                            end_date=chunk_end,
                            message=message,
                        )
                    )

                else:
                    if batch_result.failed_request_count == 0:
                        state = state.mark_completed(task_key)
                        self._save_state(state)

                        LOGGER.info(
                            "履歴取込チャンクを完了状態として保存しました。 "
                            "code=%s start_date=%s end_date=%s",
                            code,
                            chunk_start.isoformat(),
                            chunk_end.isoformat(),
                        )

                    else:
                        failure_message = (
                            self._create_batch_failure_message(
                                batch_result
                            )
                        )

                        state = state.mark_failed(
                            task_key,
                            message=failure_message,
                            attempt_count=1,
                        )
                        self._save_state(state)

                        LOGGER.warning(
                            "履歴取込チャンクに失敗リクエストが含まれるため、"
                            "未完了状態として保存しました。 "
                            "code=%s start_date=%s end_date=%s "
                            "failed_request_count=%s",
                            code,
                            chunk_start.isoformat(),
                            chunk_end.isoformat(),
                            batch_result.failed_request_count,
                        )

                symbol_request_count += batch_result.request_count
                symbol_successful_count += (
                    batch_result.successful_request_count
                )
                symbol_empty_count += batch_result.empty_request_count
                symbol_failed_count += batch_result.failed_request_count

                symbol_minute_bar_count += batch_result.minute_bar_count
                symbol_five_minute_bar_count += (
                    batch_result.five_minute_bar_count
                )
                symbol_processed_bar_count += (
                    batch_result.processed_bar_count
                )

                for failure in batch_result.failures:
                    failures.append(
                        HistoryImportFailure(
                            code=failure.code,
                            start_date=failure.target_date,
                            end_date=failure.target_date,
                            message=failure.message,
                        )
                    )

                completed_tasks += 1

                self._notify_progress(
                    progress_callback=progress_callback,
                    completed_tasks=completed_tasks,
                    total_tasks=total_tasks,
                    code=code,
                    chunk_number=chunk_number,
                    chunk_count=len(date_chunks),
                    start_date=chunk_start,
                    end_date=chunk_end,
                    batch_result=batch_result,
                )

            symbol_results.append(
                HistorySymbolResult(
                    code=code,
                    business_date_count=len(business_dates),
                    chunk_count=len(date_chunks),
                    request_count=symbol_request_count,
                    successful_request_count=symbol_successful_count,
                    empty_request_count=symbol_empty_count,
                    failed_request_count=symbol_failed_count,
                    minute_bar_count=symbol_minute_bar_count,
                    five_minute_bar_count=(
                        symbol_five_minute_bar_count
                    ),
                    processed_bar_count=symbol_processed_bar_count,
                )
            )

        return HistoryImportResult(
            start_date=start_date,
            end_date=end_date,
            code_results=symbol_results,
            failures=failures,
        )

    def _run_chunk_with_retry(
        self,
        *,
        code: str,
        target_dates: list[date],
        interval_minutes: int,
        data_source: str,
        continue_on_error: bool,
    ) -> JQuantsBatchImportResult:
        """1チャンクを再試行付きで取り込む。"""

        chunk_start = target_dates[0]
        chunk_end = target_dates[-1]

        def operation() -> JQuantsBatchImportResult:
            return self.batch_importer.run_dates(
                codes=[code],
                target_dates=target_dates,
                interval_minutes=interval_minutes,
                data_source=data_source,
                continue_on_error=continue_on_error,
            )

        def retry_callback(attempt: RetryAttempt) -> None:
            self._log_retry_attempt(
                code=code,
                start_date=chunk_start,
                end_date=chunk_end,
                attempt=attempt,
            )

        if self.retry_sleeper is None:
            return run_with_retry(
                operation,
                policy=self.retry_policy,
                retry_exceptions=self.retry_exceptions,
                retry_callback=retry_callback,
            )

        return run_with_retry(
            operation,
            policy=self.retry_policy,
            retry_exceptions=self.retry_exceptions,
            sleeper=self.retry_sleeper,
            retry_callback=retry_callback,
        )

    @staticmethod
    def _log_retry_attempt(
        *,
        code: str,
        start_date: date,
        end_date: date,
        attempt: RetryAttempt,
    ) -> None:
        """失敗した再試行をログへ記録する。"""

        LOGGER.warning(
            "履歴取込チャンクを再試行します。 "
            "code=%s start_date=%s end_date=%s "
            "attempt_number=%s delay_seconds=%s error=%s",
            code,
            start_date.isoformat(),
            end_date.isoformat(),
            attempt.attempt_number,
            attempt.delay_seconds,
            attempt.error,
        )

    def _load_state(self) -> HistoryImportState:
        """保存済み状態を読み込む。"""

        if self.state_repository is None:
            return HistoryImportState.empty()

        state = self.state_repository.load()

        LOGGER.info(
            "履歴取込状態を読み込みました。 "
            "completed_task_count=%s failure_count=%s",
            len(state.completed_task_keys),
            len(state.failures),
        )

        return state

    def _save_state(
        self,
        state: HistoryImportState,
    ) -> None:
        """状態リポジトリがある場合に現在状態を保存する。"""

        if self.state_repository is None:
            return

        saved_path = self.state_repository.save(state)

        LOGGER.debug(
            "履歴取込状態を保存しました。 path=%s",
            saved_path,
        )

    @staticmethod
    def _notify_progress(
        *,
        progress_callback: HistoryProgressCallback | None,
        completed_tasks: int,
        total_tasks: int,
        code: str,
        chunk_number: int,
        chunk_count: int,
        start_date: date,
        end_date: date,
        batch_result: JQuantsBatchImportResult,
    ) -> None:
        """進捗コールバックがある場合に現在の進捗を通知する。"""

        if progress_callback is None:
            return

        progress_callback(
            HistoryImportProgress(
                completed_tasks=completed_tasks,
                total_tasks=total_tasks,
                code=code,
                chunk_number=chunk_number,
                chunk_count=chunk_count,
                start_date=start_date,
                end_date=end_date,
                request_count=batch_result.request_count,
                successful_request_count=(
                    batch_result.successful_request_count
                ),
                empty_request_count=(
                    batch_result.empty_request_count
                ),
                failed_request_count=(
                    batch_result.failed_request_count
                ),
                minute_bar_count=batch_result.minute_bar_count,
                five_minute_bar_count=(
                    batch_result.five_minute_bar_count
                ),
                processed_bar_count=(
                    batch_result.processed_bar_count
                ),
            )
        )

    @staticmethod
    def _create_batch_failure_message(
        batch_result: JQuantsBatchImportResult,
    ) -> str:
        """一括取込結果から状態保存用の失敗メッセージを作る。"""

        failure_messages = [
            failure.message.strip()
            for failure in batch_result.failures
            if failure.message.strip()
        ]

        if failure_messages:
            unique_messages = list(dict.fromkeys(failure_messages))

            return (
                "チャンク内に失敗したリクエストがあります。 "
                f"failed_request_count="
                f"{batch_result.failed_request_count} "
                f"messages={' | '.join(unique_messages)}"
            )

        return (
            "チャンク内に失敗したリクエストがあります。 "
            f"failed_request_count="
            f"{batch_result.failed_request_count}"
        )

    @staticmethod
    def _retry_error_message(
        error: RetryExhaustedError,
    ) -> str:
        """再試行上限例外から保存用メッセージを作る。"""

        if error.last_error is not None:
            return str(error.last_error)

        return str(error)

    @staticmethod
    def _create_failed_batch_result(
        date_count: int,
        failed_count: int,
    ) -> JQuantsBatchImportResult:
        """チャンク全体が失敗した場合の結果を作成する。"""

        return JQuantsBatchImportResult(
            code_count=1,
            date_count=date_count,
            request_count=failed_count,
            successful_request_count=0,
            empty_request_count=0,
            failed_request_count=failed_count,
            minute_bar_count=0,
            five_minute_bar_count=0,
            processed_bar_count=0,
            failures=[],
        )

    @staticmethod
    def _create_skipped_batch_result(
        date_count: int,
    ) -> JQuantsBatchImportResult:
        """完了済みチャンクの進捗通知用結果を作成する。"""

        return JQuantsBatchImportResult(
            code_count=1,
            date_count=date_count,
            request_count=0,
            successful_request_count=0,
            empty_request_count=0,
            failed_request_count=0,
            minute_bar_count=0,
            five_minute_bar_count=0,
            processed_bar_count=0,
            failures=[],
        )

    @staticmethod
    def _validate_run_arguments(
        *,
        start_date: date,
        end_date: date,
        chunk_business_days: int,
        interval_minutes: int,
        data_source: str,
    ) -> None:
        """履歴取込条件を検証する。"""

        if start_date > end_date:
            raise ValueError(
                "開始日は終了日以前にしてください。"
            )

        if chunk_business_days <= 0:
            raise ValueError(
                "チャンク営業日数は0より大きい必要があります。"
            )

        if interval_minutes <= 0:
            raise ValueError(
                "時間足の間隔は0より大きい必要があります。"
            )

        if not data_source.strip():
            raise ValueError(
                "データソースを指定してください。"
            )

    @staticmethod
    def _normalize_codes(
        codes: list[str],
    ) -> list[str]:
        """銘柄コードを検証して重複を除去する。"""

        if not codes:
            raise ValueError(
                "銘柄コードを1件以上指定してください。"
            )

        normalized_codes: list[str] = []

        for code in codes:
            normalized = code.strip()

            if not normalized.isdigit():
                raise ValueError(
                    "銘柄コードは数字で指定してください。"
                )

            if len(normalized) not in (4, 5):
                raise ValueError(
                    "銘柄コードは4桁または5桁で指定してください。"
                )

            if normalized not in normalized_codes:
                normalized_codes.append(normalized)

        return normalized_codes