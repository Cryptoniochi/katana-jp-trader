"""J-Quants履歴取込フロー全体の統合テスト。"""

import csv
from datetime import date, datetime
from pathlib import Path

import pytest

from app.database import initialize_database
from app.import_jquants_history import (
    run_history_import,
    write_csv_report,
)
from app.market.bar_aggregator import (
    StockPriceAggregator,
)
from app.market.bar_repository import (
    MarketBarRepository,
)
from app.market.history_progress import (
    HistoryImportProgress,
)
from app.market.history_retry import (
    RetryExhaustedError,
    RetryPolicy,
)
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
        """設定済みの営業日一覧を返す。"""

        self.calls.append(
            (
                start_date,
                end_date,
            )
        )

        return self.business_dates


class FakeDownloader:
    """登録済みの分足を返すテスト用Downloader。"""

    def __init__(
        self,
        responses: dict[
            tuple[str, str],
            list[StockPrice],
        ],
    ) -> None:
        """銘柄・日付ごとの応答を設定する。"""

        self.responses = responses
        self.requests: list[
            tuple[str, str]
        ] = []

    def download(
        self,
        code: str,
        date: str,
    ) -> list[StockPrice]:
        """登録済みの分足一覧を返す。"""

        self.requests.append(
            (
                code,
                date,
            )
        )

        return self.responses.get(
            (
                code,
                date,
            ),
            [],
        )


class RetryThenSuccessDownloader:
    """一時例外を発生させた後に成功するDownloader。"""

    def __init__(
        self,
        response: list[StockPrice],
        *,
        failure_count: int,
    ) -> None:
        """成功前に発生させる例外回数を設定する。"""

        self.response = response
        self.failure_count = failure_count
        self.call_count = 0
        self.requests: list[
            tuple[str, str]
        ] = []

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


class AlwaysTimeoutDownloader:
    """常にTimeoutErrorを発生させるDownloader。"""

    def __init__(self) -> None:
        """呼び出し回数を初期化する。"""

        self.call_count = 0

    def download(
        self,
        code: str,
        date: str,
    ) -> list[StockPrice]:
        """常にTimeoutErrorを送出する。"""

        self.call_count += 1

        raise TimeoutError(
            "permanent timeout: "
            f"code={code} date={date} "
            f"attempt={self.call_count}"
        )


class SelectivelyFailingDownloader:
    """指定した日付だけ取得失敗するDownloader。"""

    def __init__(
        self,
        responses: dict[
            tuple[str, str],
            list[StockPrice],
        ],
        *,
        failing_requests: set[
            tuple[str, str]
        ],
    ) -> None:
        """正常応答と失敗対象を設定する。"""

        self.responses = responses
        self.failing_requests = failing_requests
        self.requests: list[
            tuple[str, str]
        ] = []

    def download(
        self,
        code: str,
        date: str,
    ) -> list[StockPrice]:
        """失敗対象ならJQuantsDownloadErrorを送出する。"""

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
    """2営業日分のテスト応答を作成する。"""

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
            create_minute_price(
                code="7203",
                date_text="2026-07-02",
                time_text="09:01",
                close=1011.0,
                volume=250,
            ),
        ],
    }


def create_repository(
    temporary_path: Path,
) -> MarketBarRepository:
    """初期化済みSQLite Repositoryを作成する。"""

    database_path = (
        temporary_path / "katana.db"
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
    """統合テスト用一括取込サービスを作成する。"""

    return JQuantsBatchImportService(
        downloader=downloader,
        aggregator=StockPriceAggregator(),
        repository=repository,
        request_interval_seconds=0,
        sleeper=lambda _seconds: None,
    )


def read_csv_rows(
    file_path: Path,
) -> list[dict[str, str]]:
    """CSVレポートを辞書一覧として読み込む。"""

    with file_path.open(
        mode="r",
        encoding="utf-8-sig",
        newline="",
    ) as csv_file:
        return list(
            csv.DictReader(csv_file)
        )


def test_history_import_end_to_end_creates_database_state_and_csv(
    tmp_path: Path,
) -> None:
    """初回取込でDB・状態JSON・CSVを作成する。"""

    repository = create_repository(
        tmp_path
    )
    state_path = (
        tmp_path / "state" / "history.json"
    )
    report_path = (
        tmp_path / "reports" / "history.csv"
    )

    downloader = FakeDownloader(
        create_standard_responses()
    )

    batch_service = create_batch_service(
        downloader=downloader,
        repository=repository,
    )

    progress: list[
        HistoryImportProgress
    ] = []

    result = run_history_import(
        codes=["7203"],
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 2),
        chunk_business_days=1,
        request_interval_seconds=0,
        continue_on_error=True,
        state_file_path=state_path,
        calendar_reader=FakeCalendarReader(
            [
                date(2026, 7, 1),
                date(2026, 7, 2),
            ]
        ),
        batch_importer=batch_service,
        progress_callback=progress.append,
    )

    saved_report_path = write_csv_report(
        result=result,
        output_path=report_path,
    )

    assert result.code_count == 1
    assert result.chunk_count == 2
    assert result.request_count == 2
    assert result.successful_request_count == 2
    assert result.failed_request_count == 0
    assert result.minute_bar_count == 4
    assert result.five_minute_bar_count == 2
    assert result.processed_bar_count == 2

    assert downloader.requests == [
        (
            "7203",
            "2026-07-01",
        ),
        (
            "7203",
            "2026-07-02",
        ),
    ]

    assert repository.count(
        code="7203",
        interval_minutes=5,
    ) == 2

    loaded_prices = repository.read(
        code="7203",
        interval_minutes=5,
    )

    assert len(loaded_prices) == 2
    assert loaded_prices[0].datetime == datetime(
        2026,
        7,
        1,
        9,
        0,
    )
    assert loaded_prices[1].datetime == datetime(
        2026,
        7,
        2,
        9,
        0,
    )

    state_repository = HistoryStateRepository(
        state_path
    )
    state = state_repository.load()

    first_key = HistoryTaskKey(
        code="7203",
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 1),
    )
    second_key = HistoryTaskKey(
        code="7203",
        start_date=date(2026, 7, 2),
        end_date=date(2026, 7, 2),
    )

    assert state.is_completed(
        first_key
    )
    assert state.is_completed(
        second_key
    )
    assert state.failures == ()

    assert len(progress) == 2
    assert progress[0].completed_tasks == 1
    assert progress[1].completed_tasks == 2
    assert progress[1].completion_rate == (
        pytest.approx(100.0)
    )

    assert saved_report_path == report_path
    assert report_path.exists()

    csv_rows = read_csv_rows(
        report_path
    )

    assert len(csv_rows) == 2
    assert csv_rows[0]["record_type"] == (
        "summary"
    )
    assert csv_rows[1]["record_type"] == (
        "symbol"
    )
    assert csv_rows[1]["code"] == "7203"
    assert csv_rows[1]["request_count"] == "2"
    assert csv_rows[1]["processed_bar_count"] == "2"


def test_history_import_rerun_skips_completed_chunks_and_keeps_db_count(
    tmp_path: Path,
) -> None:
    """再実行時に完了済みチャンクをスキップする。"""

    repository = create_repository(
        tmp_path
    )
    state_path = (
        tmp_path / "history_state.json"
    )
    report_path = (
        tmp_path / "rerun_report.csv"
    )

    first_downloader = FakeDownloader(
        create_standard_responses()
    )

    first_result = run_history_import(
        codes=["7203"],
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 2),
        chunk_business_days=1,
        request_interval_seconds=0,
        continue_on_error=True,
        state_file_path=state_path,
        calendar_reader=FakeCalendarReader(
            [
                date(2026, 7, 1),
                date(2026, 7, 2),
            ]
        ),
        batch_importer=create_batch_service(
            downloader=first_downloader,
            repository=repository,
        ),
    )

    assert first_result.request_count == 2
    assert repository.count(
        code="7203",
        interval_minutes=5,
    ) == 2

    second_downloader = FakeDownloader(
        create_standard_responses()
    )

    progress: list[
        HistoryImportProgress
    ] = []

    second_result = run_history_import(
        codes=["7203"],
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 2),
        chunk_business_days=1,
        request_interval_seconds=0,
        continue_on_error=True,
        state_file_path=state_path,
        calendar_reader=FakeCalendarReader(
            [
                date(2026, 7, 1),
                date(2026, 7, 2),
            ]
        ),
        batch_importer=create_batch_service(
            downloader=second_downloader,
            repository=repository,
        ),
        progress_callback=progress.append,
    )

    write_csv_report(
        result=second_result,
        output_path=report_path,
    )

    assert second_downloader.requests == []
    assert second_result.request_count == 0
    assert second_result.successful_request_count == 0
    assert second_result.failed_request_count == 0
    assert second_result.processed_bar_count == 0

    assert repository.count(
        code="7203",
        interval_minutes=5,
    ) == 2

    assert len(progress) == 2
    assert progress[0].request_count == 0
    assert progress[1].request_count == 0
    assert progress[1].completion_rate == (
        pytest.approx(100.0)
    )

    csv_rows = read_csv_rows(
        report_path
    )

    assert csv_rows[0]["record_type"] == (
        "summary"
    )
    assert csv_rows[0]["request_count"] == "0"
    assert csv_rows[1]["record_type"] == (
        "symbol"
    )
    assert csv_rows[1]["processed_bar_count"] == "0"


def test_history_import_retries_timeout_and_completes_integration_flow(
    tmp_path: Path,
) -> None:
    """一時的なTimeoutErrorを再試行して正常完了する。"""

    repository = create_repository(
        tmp_path
    )
    state_path = (
        tmp_path / "retry_state.json"
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
        response,
        failure_count=2,
    )

    sleep_calls: list[float] = []

    result = run_history_import(
        codes=["7203"],
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 1),
        chunk_business_days=1,
        request_interval_seconds=0,
        continue_on_error=True,
        state_file_path=state_path,
        retry_policy=RetryPolicy(
            max_attempts=3,
            initial_delay_seconds=0.25,
            backoff_multiplier=2.0,
            maximum_delay_seconds=1.0,
        ),
        retry_sleeper=sleep_calls.append,
        calendar_reader=FakeCalendarReader(
            [
                date(2026, 7, 1),
            ]
        ),
        batch_importer=create_batch_service(
            downloader=downloader,
            repository=repository,
        ),
    )

    assert downloader.call_count == 3
    assert sleep_calls == [
        0.25,
        0.5,
    ]

    assert result.request_count == 1
    assert result.successful_request_count == 1
    assert result.failed_request_count == 0
    assert result.processed_bar_count == 1

    assert repository.count(
        code="7203",
        interval_minutes=5,
    ) == 1

    state = HistoryStateRepository(
        state_path
    ).load()

    key = HistoryTaskKey(
        code="7203",
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 1),
    )

    assert state.is_completed(key)
    assert state.failures == ()


def test_history_import_partial_failure_is_saved_and_resumed(
    tmp_path: Path,
) -> None:
    """部分失敗を保存し、次回実行で失敗チャンクを再開する。"""

    repository = create_repository(
        tmp_path
    )
    state_path = (
        tmp_path / "resume_state.json"
    )
    failed_report_path = (
        tmp_path / "failed_report.csv"
    )
    resumed_report_path = (
        tmp_path / "resumed_report.csv"
    )

    responses = create_standard_responses()

    failing_downloader = SelectivelyFailingDownloader(
        responses,
        failing_requests={
            (
                "7203",
                "2026-07-02",
            )
        },
    )

    first_result = run_history_import(
        codes=["7203"],
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 2),
        chunk_business_days=2,
        request_interval_seconds=0,
        continue_on_error=True,
        state_file_path=state_path,
        calendar_reader=FakeCalendarReader(
            [
                date(2026, 7, 1),
                date(2026, 7, 2),
            ]
        ),
        batch_importer=create_batch_service(
            downloader=failing_downloader,
            repository=repository,
        ),
    )

    write_csv_report(
        result=first_result,
        output_path=failed_report_path,
    )

    assert first_result.request_count == 2
    assert first_result.successful_request_count == 1
    assert first_result.failed_request_count == 1
    assert len(first_result.failures) == 1

    assert repository.count(
        code="7203",
        interval_minutes=5,
    ) == 1

    task_key = HistoryTaskKey(
        code="7203",
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 2),
    )

    failed_state = HistoryStateRepository(
        state_path
    ).load()

    assert not failed_state.is_completed(
        task_key
    )
    assert len(failed_state.failures) == 1
    assert (
        "integration download failure"
        in failed_state.failures[0].message
    )

    failed_csv_rows = read_csv_rows(
        failed_report_path
    )

    assert len(failed_csv_rows) == 3
    assert failed_csv_rows[2]["record_type"] == (
        "failure"
    )
    assert failed_csv_rows[2]["code"] == "7203"
    assert (
        "integration download failure"
        in failed_csv_rows[2]["message"]
    )

    successful_downloader = FakeDownloader(
        responses
    )

    second_result = run_history_import(
        codes=["7203"],
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 2),
        chunk_business_days=2,
        request_interval_seconds=0,
        continue_on_error=True,
        state_file_path=state_path,
        calendar_reader=FakeCalendarReader(
            [
                date(2026, 7, 1),
                date(2026, 7, 2),
            ]
        ),
        batch_importer=create_batch_service(
            downloader=successful_downloader,
            repository=repository,
        ),
    )

    write_csv_report(
        result=second_result,
        output_path=resumed_report_path,
    )

    assert successful_downloader.requests == [
        (
            "7203",
            "2026-07-01",
        ),
        (
            "7203",
            "2026-07-02",
        ),
    ]

    assert second_result.request_count == 2
    assert second_result.successful_request_count == 2
    assert second_result.failed_request_count == 0

    assert repository.count(
        code="7203",
        interval_minutes=5,
    ) == 2

    resumed_state = HistoryStateRepository(
        state_path
    ).load()

    assert resumed_state.is_completed(
        task_key
    )
    assert resumed_state.failures == ()

    resumed_csv_rows = read_csv_rows(
        resumed_report_path
    )

    assert len(resumed_csv_rows) == 2
    assert resumed_csv_rows[0]["record_type"] == (
        "summary"
    )
    assert resumed_csv_rows[1]["record_type"] == (
        "symbol"
    )
    assert resumed_csv_rows[1][
        "failed_request_count"
    ] == "0"


def test_history_import_retry_exhaustion_saves_failure_before_raise(
    tmp_path: Path,
) -> None:
    """停止モードでは再試行失敗を保存してから例外を送出する。"""

    repository = create_repository(
        tmp_path
    )
    state_path = (
        tmp_path / "exhausted_state.json"
    )

    downloader = AlwaysTimeoutDownloader()
    sleep_calls: list[float] = []

    with pytest.raises(
        RetryExhaustedError,
    ):
        run_history_import(
            codes=["7203"],
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 1),
            chunk_business_days=1,
            request_interval_seconds=0,
            continue_on_error=False,
            state_file_path=state_path,
            retry_policy=RetryPolicy(
                max_attempts=3,
                initial_delay_seconds=0.1,
                backoff_multiplier=2.0,
                maximum_delay_seconds=1.0,
            ),
            retry_sleeper=sleep_calls.append,
            calendar_reader=FakeCalendarReader(
                [
                    date(2026, 7, 1),
                ]
            ),
            batch_importer=create_batch_service(
                downloader=downloader,
                repository=repository,
            ),
        )

    assert downloader.call_count == 3
    assert sleep_calls == [
        0.1,
        0.2,
    ]

    assert repository.count(
        code="7203",
        interval_minutes=5,
    ) == 0

    state = HistoryStateRepository(
        state_path
    ).load()

    key = HistoryTaskKey(
        code="7203",
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 1),
    )

    assert not state.is_completed(
        key
    )
    assert len(state.failures) == 1
    assert state.failures[0].attempt_count == 3
    assert (
        "permanent timeout"
        in state.failures[0].message
    )


def test_history_import_multiple_codes_preserves_code_separation(
    tmp_path: Path,
) -> None:
    """複数銘柄をDB・状態・CSVで分離して処理する。"""

    repository = create_repository(
        tmp_path
    )
    state_path = (
        tmp_path / "multiple_codes_state.json"
    )
    report_path = (
        tmp_path / "multiple_codes_report.csv"
    )

    responses = {
        (
            "7203",
            "2026-07-01",
        ): [
            create_minute_price(
                code="7203",
                date_text="2026-07-01",
                time_text="09:00",
                close=1000.0,
            )
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
            )
        ],
    }

    downloader = FakeDownloader(
        responses
    )

    result = run_history_import(
        codes=["7203", "8306"],
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 1),
        chunk_business_days=1,
        request_interval_seconds=0,
        continue_on_error=True,
        state_file_path=state_path,
        calendar_reader=FakeCalendarReader(
            [
                date(2026, 7, 1),
            ]
        ),
        batch_importer=create_batch_service(
            downloader=downloader,
            repository=repository,
        ),
    )

    write_csv_report(
        result=result,
        output_path=report_path,
    )

    assert result.code_count == 2
    assert result.chunk_count == 2
    assert result.request_count == 2
    assert result.successful_request_count == 2

    assert repository.count(
        code="7203",
        interval_minutes=5,
    ) == 1

    assert repository.count(
        code="8306",
        interval_minutes=5,
    ) == 1

    state = HistoryStateRepository(
        state_path
    ).load()

    first_key = HistoryTaskKey(
        code="7203",
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 1),
    )
    second_key = HistoryTaskKey(
        code="8306",
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 1),
    )

    assert state.is_completed(
        first_key
    )
    assert state.is_completed(
        second_key
    )

    csv_rows = read_csv_rows(
        report_path
    )

    assert len(csv_rows) == 3

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