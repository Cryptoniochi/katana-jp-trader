"""J-Quants自動差分更新基盤の統合テスト。"""

import csv
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from app.database import initialize_database
from app.market.bar_aggregator import StockPriceAggregator
from app.market.bar_repository import MarketBarRepository
from app.market.history_retry import RetryPolicy
from app.market.history_state import (
    HistoryStateRepository,
    HistoryTaskKey,
)
from app.market.jquants_batch_import import (
    JQuantsBatchImportService,
)
from app.market.jquants_downloader import (
    JQuantsDownloadError,
)
from app.market.models import StockPrice
from app.market.process_lock import (
    AlreadyLockedError,
    ProcessLock,
)
from app.update_jquants_history import (
    EXIT_PARTIAL_FAILURE,
    EXIT_SUCCESS,
    determine_exit_code,
    run_incremental_update,
    run_locked_incremental_update,
)


class FakeCalendarReader:
    """テスト用の取引カレンダー。"""

    def __init__(
        self,
        business_dates: list[date],
    ) -> None:
        """返却する営業日を設定する。"""

        self.business_dates = business_dates
        self.calls: list[tuple[date, date]] = []

    def get_business_dates(
        self,
        start_date: date,
        end_date: date,
    ) -> list[date]:
        """指定範囲内の営業日を返す。"""

        self.calls.append(
            (
                start_date,
                end_date,
            )
        )

        return [
            business_date
            for business_date in self.business_dates
            if start_date <= business_date <= end_date
        ]


class FakeDownloader:
    """登録済みの1分足を返すDownloader。"""

    def __init__(
        self,
        responses: dict[
            tuple[str, str],
            list[StockPrice],
        ],
    ) -> None:
        """銘柄・日付別の応答を設定する。"""

        self.responses = responses
        self.requests: list[tuple[str, str]] = []

    def download(
        self,
        code: str,
        date: str,
    ) -> list[StockPrice]:
        """登録済みの応答を返す。"""

        request = (
            code,
            date,
        )

        self.requests.append(request)

        return self.responses.get(
            request,
            [],
        )


class SelectivelyFailingDownloader:
    """指定した銘柄・日付だけ失敗するDownloader。"""

    def __init__(
        self,
        responses: dict[
            tuple[str, str],
            list[StockPrice],
        ],
        failing_requests: set[
            tuple[str, str]
        ],
    ) -> None:
        """正常応答と失敗対象を設定する。"""

        self.responses = responses
        self.failing_requests = failing_requests
        self.requests: list[tuple[str, str]] = []

    def download(
        self,
        code: str,
        date: str,
    ) -> list[StockPrice]:
        """失敗対象なら取得例外を送出する。"""

        request = (
            code,
            date,
        )

        self.requests.append(request)

        if request in self.failing_requests:
            raise JQuantsDownloadError(
                "integration download failure: "
                f"code={code} date={date}"
            )

        return self.responses.get(
            request,
            [],
        )


class RetryThenSuccessDownloader:
    """一時失敗後に成功するDownloader。"""

    def __init__(
        self,
        response: list[StockPrice],
        *,
        failure_count: int,
    ) -> None:
        """成功前に発生させる失敗回数を設定する。"""

        self.response = response
        self.failure_count = failure_count
        self.call_count = 0
        self.requests: list[tuple[str, str]] = []

    def download(
        self,
        code: str,
        date: str,
    ) -> list[StockPrice]:
        """指定回数だけTimeoutErrorを送出する。"""

        self.call_count += 1

        self.requests.append(
            (
                code,
                date,
            )
        )

        if self.call_count <= self.failure_count:
            raise TimeoutError(
                f"temporary timeout {self.call_count}"
            )

        return self.response


def create_minute_price(
    code: str,
    date_text: str,
    time_text: str,
    *,
    close: float,
    volume: int = 100,
) -> StockPrice:
    """統合テスト用の1分足を作成する。"""

    return StockPrice(
        code=code,
        datetime=datetime.strptime(
            f"{date_text} {time_text}",
            "%Y-%m-%d %H:%M",
        ),
        open=close,
        high=close + 1.0,
        low=close - 1.0,
        close=close,
        volume=volume,
    )


def create_standard_responses() -> dict[
    tuple[str, str],
    list[StockPrice],
]:
    """複数銘柄・複数営業日の応答を作成する。"""

    return {
        (
            "7203",
            "2026-07-01",
        ): [
            create_minute_price(
                code="7203",
                date_text="2026-07-01",
                time_text="09:00",
                close=1000.0,
                volume=100,
            ),
            create_minute_price(
                code="7203",
                date_text="2026-07-01",
                time_text="09:01",
                close=1001.0,
                volume=150,
            ),
        ],
        (
            "7203",
            "2026-07-02",
        ): [
            create_minute_price(
                code="7203",
                date_text="2026-07-02",
                time_text="09:00",
                close=1010.0,
                volume=200,
            ),
        ],
        (
            "7203",
            "2026-07-03",
        ): [
            create_minute_price(
                code="7203",
                date_text="2026-07-03",
                time_text="09:00",
                close=1020.0,
                volume=300,
            ),
        ],
        (
            "8306",
            "2026-07-01",
        ): [
            create_minute_price(
                code="8306",
                date_text="2026-07-01",
                time_text="09:00",
                close=2000.0,
                volume=100,
            ),
        ],
        (
            "8306",
            "2026-07-02",
        ): [
            create_minute_price(
                code="8306",
                date_text="2026-07-02",
                time_text="09:00",
                close=2010.0,
                volume=200,
            ),
        ],
        (
            "8306",
            "2026-07-03",
        ): [
            create_minute_price(
                code="8306",
                date_text="2026-07-03",
                time_text="09:00",
                close=2020.0,
                volume=300,
            ),
        ],
    }


def create_repository(
    tmp_path: Path,
) -> MarketBarRepository:
    """初期化済みSQLite Repositoryを作成する。"""

    database_path = (
        tmp_path / "katana.db"
    )

    initialize_database(
        database_path
    )

    return MarketBarRepository(
        database_path
    )


def create_batch_service(
    *,
    downloader: object,
    repository: MarketBarRepository,
) -> JQuantsBatchImportService:
    """統合テスト用の一括取込サービスを作成する。"""

    return JQuantsBatchImportService(
        downloader=downloader,
        aggregator=StockPriceAggregator(),
        repository=repository,
        request_interval_seconds=0,
        sleeper=lambda _seconds: None,
    )


def create_process_lock(
    lock_path: Path,
    *,
    lock_id: str,
) -> ProcessLock:
    """固定情報を使うプロセスロックを作成する。"""

    return ProcessLock(
        file_path=lock_path,
        process_name=(
            "jquants-incremental-integration-test"
        ),
        stale_after_seconds=3600,
        now_provider=lambda: datetime(
            2026,
            7,
            16,
            tzinfo=timezone.utc,
        ),
        pid_provider=lambda: 12345,
        hostname_provider=lambda: "test-host",
        lock_id_provider=lambda: lock_id,
    )


def read_csv_rows(
    report_path: Path,
) -> list[dict[str, str]]:
    """CSVレポートを辞書一覧として読み込む。"""

    with report_path.open(
        mode="r",
        encoding="utf-8-sig",
        newline="",
    ) as csv_file:
        return list(
            csv.DictReader(csv_file)
        )


def test_incremental_update_end_to_end_creates_db_state_report_and_releases_lock(
    tmp_path: Path,
) -> None:
    """初回差分更新でDB・状態・CSVを生成しロックを解放する。"""

    repository = create_repository(
        tmp_path
    )
    state_path = (
        tmp_path / "state" / "update.json"
    )
    report_path = (
        tmp_path / "reports" / "update.csv"
    )
    lock_path = (
        tmp_path / "locks" / "update.lock"
    )

    downloader = FakeDownloader(
        create_standard_responses()
    )

    result = run_locked_incremental_update(
        process_lock=create_process_lock(
            lock_path,
            lock_id="initial-lock",
        ),
        codes=[
            "7203",
            "8306",
        ],
        initial_start_date=date(
            2026,
            7,
            1,
        ),
        target_end_date=date(
            2026,
            7,
            3,
        ),
        chunk_business_days=2,
        request_interval_seconds=0,
        continue_on_error=True,
        repository=repository,
        calendar_reader=FakeCalendarReader(
            [
                date(2026, 7, 1),
                date(2026, 7, 2),
                date(2026, 7, 3),
            ]
        ),
        state_repository=HistoryStateRepository(
            state_path
        ),
        retry_policy=RetryPolicy(
            max_attempts=1,
            initial_delay_seconds=0,
            backoff_multiplier=1,
            maximum_delay_seconds=0,
        ),
        batch_importer=create_batch_service(
            downloader=downloader,
            repository=repository,
        ),
        retry_sleeper=lambda _seconds: None,
        report_path=report_path,
        today=date(
            2026,
            7,
            16,
        ),
    )

    assert result.plan.code_count == 2
    assert result.plan.update_code_count == 2
    assert result.plan.skipped_code_count == 0

    assert result.history_result.code_count == 2
    assert result.history_result.request_count == 6
    assert (
        result.history_result.successful_request_count
        == 6
    )
    assert (
        result.history_result.failed_request_count
        == 0
    )
    assert (
        result.history_result.processed_bar_count
        == 6
    )

    assert determine_exit_code(
        result
    ) == EXIT_SUCCESS

    assert repository.count(
        code="7203",
        interval_minutes=5,
    ) == 3

    assert repository.count(
        code="8306",
        interval_minutes=5,
    ) == 3

    assert repository.count(
        interval_minutes=5,
    ) == 6

    state = HistoryStateRepository(
        state_path
    ).load()

    expected_keys = [
        HistoryTaskKey(
            code="7203",
            start_date=date(
                2026,
                7,
                1,
            ),
            end_date=date(
                2026,
                7,
                2,
            ),
        ),
        HistoryTaskKey(
            code="7203",
            start_date=date(
                2026,
                7,
                3,
            ),
            end_date=date(
                2026,
                7,
                3,
            ),
        ),
        HistoryTaskKey(
            code="8306",
            start_date=date(
                2026,
                7,
                1,
            ),
            end_date=date(
                2026,
                7,
                2,
            ),
        ),
        HistoryTaskKey(
            code="8306",
            start_date=date(
                2026,
                7,
                3,
            ),
            end_date=date(
                2026,
                7,
                3,
            ),
        ),
    ]

    for key in expected_keys:
        assert state.is_completed(key)

    assert state.failures == ()

    assert report_path.exists()
    assert result.report_path == report_path

    csv_rows = read_csv_rows(
        report_path
    )

    assert len(csv_rows) == 3
    assert csv_rows[0]["record_type"] == "summary"

    symbol_rows = [
        row
        for row in csv_rows
        if row["record_type"] == "symbol"
    ]

    assert {
        row["code"]
        for row in symbol_rows
    } == {
        "7203",
        "8306",
    }

    assert lock_path.exists() is False


def test_incremental_update_second_run_skips_all_and_keeps_database_unchanged(
    tmp_path: Path,
) -> None:
    """同一終了日の再実行では全銘柄をスキップする。"""

    repository = create_repository(
        tmp_path
    )
    state_path = (
        tmp_path / "state.json"
    )

    first_downloader = FakeDownloader(
        create_standard_responses()
    )

    first_result = run_incremental_update(
        codes=[
            "7203",
            "8306",
        ],
        initial_start_date=date(
            2026,
            7,
            1,
        ),
        target_end_date=date(
            2026,
            7,
            3,
        ),
        chunk_business_days=3,
        request_interval_seconds=0,
        continue_on_error=True,
        repository=repository,
        calendar_reader=FakeCalendarReader(
            [
                date(2026, 7, 1),
                date(2026, 7, 2),
                date(2026, 7, 3),
            ]
        ),
        state_repository=HistoryStateRepository(
            state_path
        ),
        batch_importer=create_batch_service(
            downloader=first_downloader,
            repository=repository,
        ),
        retry_sleeper=lambda _seconds: None,
        today=date(
            2026,
            7,
            16,
        ),
    )

    assert first_result.history_result.request_count == 6
    assert repository.count(
        interval_minutes=5,
    ) == 6

    second_downloader = FakeDownloader(
        create_standard_responses()
    )

    second_result = run_incremental_update(
        codes=[
            "7203",
            "8306",
        ],
        initial_start_date=date(
            2026,
            7,
            1,
        ),
        target_end_date=date(
            2026,
            7,
            3,
        ),
        chunk_business_days=3,
        request_interval_seconds=0,
        continue_on_error=True,
        repository=repository,
        calendar_reader=FakeCalendarReader(
            [
                date(2026, 7, 1),
                date(2026, 7, 2),
                date(2026, 7, 3),
            ]
        ),
        state_repository=HistoryStateRepository(
            state_path
        ),
        batch_importer=create_batch_service(
            downloader=second_downloader,
            repository=repository,
        ),
        retry_sleeper=lambda _seconds: None,
        today=date(
            2026,
            7,
            16,
        ),
    )

    assert second_result.plan.update_code_count == 0
    assert second_result.plan.skipped_code_count == 2
    assert second_result.plan.is_up_to_date is True

    assert second_result.history_result.request_count == 0
    assert (
        second_result.history_result.processed_bar_count
        == 0
    )

    assert second_downloader.requests == []

    assert repository.count(
        interval_minutes=5,
    ) == 6

    assert determine_exit_code(
        second_result
    ) == EXIT_SUCCESS


def test_incremental_update_only_downloads_new_business_date(
    tmp_path: Path,
) -> None:
    """保存済み最終日の翌営業日だけを差分取得する。"""

    repository = create_repository(
        tmp_path
    )
    responses = create_standard_responses()

    initial_downloader = FakeDownloader(
        responses
    )

    run_incremental_update(
        codes=["7203"],
        initial_start_date=date(
            2026,
            7,
            1,
        ),
        target_end_date=date(
            2026,
            7,
            2,
        ),
        chunk_business_days=20,
        request_interval_seconds=0,
        continue_on_error=True,
        repository=repository,
        calendar_reader=FakeCalendarReader(
            [
                date(2026, 7, 1),
                date(2026, 7, 2),
            ]
        ),
        state_repository=HistoryStateRepository(
            tmp_path / "first_state.json"
        ),
        batch_importer=create_batch_service(
            downloader=initial_downloader,
            repository=repository,
        ),
        retry_sleeper=lambda _seconds: None,
        today=date(
            2026,
            7,
            16,
        ),
    )

    assert repository.count(
        code="7203",
        interval_minutes=5,
    ) == 2

    incremental_downloader = FakeDownloader(
        responses
    )

    result = run_incremental_update(
        codes=["7203"],
        initial_start_date=date(
            2026,
            7,
            1,
        ),
        target_end_date=date(
            2026,
            7,
            3,
        ),
        chunk_business_days=20,
        request_interval_seconds=0,
        continue_on_error=True,
        repository=repository,
        calendar_reader=FakeCalendarReader(
            [
                date(2026, 7, 1),
                date(2026, 7, 2),
                date(2026, 7, 3),
            ]
        ),
        state_repository=HistoryStateRepository(
            tmp_path / "second_state.json"
        ),
        batch_importer=create_batch_service(
            downloader=incremental_downloader,
            repository=repository,
        ),
        retry_sleeper=lambda _seconds: None,
        today=date(
            2026,
            7,
            16,
        ),
    )

    assert incremental_downloader.requests == [
        (
            "7203",
            "2026-07-03",
        )
    ]

    assert result.history_result.request_count == 1
    assert (
        result.history_result.successful_request_count
        == 1
    )
    assert (
        result.history_result.processed_bar_count
        == 1
    )

    assert repository.count(
        code="7203",
        interval_minutes=5,
    ) == 3

    assert repository.latest_datetime(
        code="7203",
        interval_minutes=5,
    ) == datetime(
        2026,
        7,
        3,
        9,
        0,
    )


def test_incremental_update_partial_failure_is_reported_and_resumed(
    tmp_path: Path,
) -> None:
    """失敗チャンクを保存し、次回実行で再取得して完了させる。"""

    repository = create_repository(
        tmp_path
    )
    state_path = (
        tmp_path / "resume_state.json"
    )
    failure_report_path = (
        tmp_path / "failure.csv"
    )
    resumed_report_path = (
        tmp_path / "resumed.csv"
    )

    responses = create_standard_responses()

    failing_downloader = (
        SelectivelyFailingDownloader(
            responses=responses,
            failing_requests={
                (
                    "7203",
                    "2026-07-02",
                )
            },
        )
    )

    first_result = run_incremental_update(
        codes=["7203"],
        initial_start_date=date(
            2026,
            7,
            1,
        ),
        target_end_date=date(
            2026,
            7,
            2,
        ),
        chunk_business_days=2,
        request_interval_seconds=0,
        continue_on_error=True,
        repository=repository,
        calendar_reader=FakeCalendarReader(
            [
                date(2026, 7, 1),
                date(2026, 7, 2),
            ]
        ),
        state_repository=HistoryStateRepository(
            state_path
        ),
        batch_importer=create_batch_service(
            downloader=failing_downloader,
            repository=repository,
        ),
        retry_sleeper=lambda _seconds: None,
        report_path=failure_report_path,
        today=date(
            2026,
            7,
            16,
        ),
    )

    assert first_result.history_result.request_count == 2
    assert (
        first_result.history_result.successful_request_count
        == 1
    )
    assert (
        first_result.history_result.failed_request_count
        == 1
    )

    assert determine_exit_code(
        first_result
    ) == EXIT_PARTIAL_FAILURE

    assert repository.count(
        code="7203",
        interval_minutes=5,
    ) == 1

    task_key = HistoryTaskKey(
        code="7203",
        start_date=date(
            2026,
            7,
            1,
        ),
        end_date=date(
            2026,
            7,
            2,
        ),
    )

    failed_state = HistoryStateRepository(
        state_path
    ).load()

    assert not failed_state.is_completed(
        task_key
    )
    assert len(
        failed_state.failures
    ) == 1

    failed_rows = read_csv_rows(
        failure_report_path
    )

    assert any(
        row["record_type"] == "failure"
        for row in failed_rows
    )

    successful_downloader = FakeDownloader(
        responses
    )

    second_result = run_incremental_update(
        codes=["7203"],
        initial_start_date=date(
            2026,
            7,
            1,
        ),
        target_end_date=date(
            2026,
            7,
            2,
        ),
        chunk_business_days=2,
        request_interval_seconds=0,
        continue_on_error=True,
        repository=repository,
        calendar_reader=FakeCalendarReader(
            [
                date(2026, 7, 1),
                date(2026, 7, 2),
            ]
        ),
        state_repository=HistoryStateRepository(
            state_path
        ),
        batch_importer=create_batch_service(
            downloader=successful_downloader,
            repository=repository,
        ),
        retry_sleeper=lambda _seconds: None,
        report_path=resumed_report_path,
        today=date(
            2026,
            7,
            16,
        ),
    )

    assert successful_downloader.requests == [
        (
            "7203",
            "2026-07-02",
        )
    ]

    assert second_result.history_result.request_count == 1
    assert (
        second_result.history_result.failed_request_count
        == 0
    )

    assert determine_exit_code(
        second_result
    ) == EXIT_SUCCESS

    assert repository.count(
        code="7203",
        interval_minutes=5,
    ) == 2

    resumed_state = HistoryStateRepository(
        state_path
    ).load()

    resumed_key = HistoryTaskKey(
        code="7203",
        start_date=date(
            2026,
            7,
            2,
        ),
        end_date=date(
            2026,
            7,
            2,
        ),
    )

    assert resumed_state.is_completed(
        resumed_key
    )
    assert resumed_state.failures == ()

    resumed_rows = read_csv_rows(
        resumed_report_path
    )

    assert not any(
        row["record_type"] == "failure"
        for row in resumed_rows
    )


def test_incremental_update_retries_temporary_failure_before_success(
    tmp_path: Path,
) -> None:
    """一時的な通信失敗を再試行してDBへ保存する。"""

    repository = create_repository(
        tmp_path
    )

    response = [
        create_minute_price(
            code="7203",
            date_text="2026-07-01",
            time_text="09:00",
            close=1000.0,
        )
    ]

    downloader = RetryThenSuccessDownloader(
        response=response,
        failure_count=2,
    )

    sleep_calls: list[float] = []

    result = run_incremental_update(
        codes=["7203"],
        initial_start_date=date(
            2026,
            7,
            1,
        ),
        target_end_date=date(
            2026,
            7,
            1,
        ),
        chunk_business_days=1,
        request_interval_seconds=0,
        continue_on_error=True,
        repository=repository,
        calendar_reader=FakeCalendarReader(
            [
                date(2026, 7, 1),
            ]
        ),
        state_repository=HistoryStateRepository(
            tmp_path / "retry_state.json"
        ),
        retry_policy=RetryPolicy(
            max_attempts=3,
            initial_delay_seconds=0.25,
            backoff_multiplier=2.0,
            maximum_delay_seconds=1.0,
        ),
        batch_importer=create_batch_service(
            downloader=downloader,
            repository=repository,
        ),
        retry_sleeper=sleep_calls.append,
        today=date(
            2026,
            7,
            16,
        ),
    )

    assert downloader.call_count == 3
    assert sleep_calls == [
        0.25,
        0.5,
    ]

    assert result.history_result.request_count == 1
    assert (
        result.history_result.failed_request_count
        == 0
    )

    assert repository.count(
        code="7203",
        interval_minutes=5,
    ) == 1


def test_locked_incremental_update_rejects_concurrent_execution(
    tmp_path: Path,
) -> None:
    """既存ロックがある場合は二重実行を拒否する。"""

    lock_path = (
        tmp_path / "update.lock"
    )

    first_lock = create_process_lock(
        lock_path,
        lock_id="first-lock",
    )
    first_lock.acquire()

    second_lock = create_process_lock(
        lock_path,
        lock_id="second-lock",
    )

    repository = create_repository(
        tmp_path
    )
    downloader = FakeDownloader(
        create_standard_responses()
    )

    with pytest.raises(
        AlreadyLockedError,
    ):
        run_locked_incremental_update(
            process_lock=second_lock,
            codes=["7203"],
            initial_start_date=date(
                2026,
                7,
                1,
            ),
            target_end_date=date(
                2026,
                7,
                1,
            ),
            chunk_business_days=1,
            request_interval_seconds=0,
            continue_on_error=True,
            repository=repository,
            calendar_reader=FakeCalendarReader(
                [
                    date(2026, 7, 1),
                ]
            ),
            state_repository=HistoryStateRepository(
                tmp_path / "state.json"
            ),
            batch_importer=create_batch_service(
                downloader=downloader,
                repository=repository,
            ),
            retry_sleeper=lambda _seconds: None,
            today=date(
                2026,
                7,
                16,
            ),
        )

    assert downloader.requests == []
    assert repository.count(
        interval_minutes=5,
    ) == 0

    first_lock.release()

    assert lock_path.exists() is False