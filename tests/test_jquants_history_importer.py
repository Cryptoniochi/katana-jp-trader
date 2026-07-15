"""J-Quants履歴データ取込基盤のテスト。"""

from datetime import date
import logging
from pathlib import Path

import pytest

from app.market.date_range import (
    create_date_range,
    filter_date_range,
    split_dates,
)
from app.market.history_progress import (
    HistoryImportProgress,
)
from app.market.history_retry import (
    RetryExhaustedError,
    RetryPolicy,
)
from app.market.history_state import (
    HistoryImportState,
    HistoryStateRepository,
    HistoryTaskKey,
)
from app.market.jquants_batch_import import (
    JQuantsBatchImportResult,
    JQuantsImportFailure,
)
from app.market.jquants_history_importer import (
    JQuantsHistoryImporter,
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
        """設定済みの営業日一覧を返す。"""

        self.calls.append((start_date, end_date))

        return self.business_dates


class FakeBatchImporter:
    """テスト用の一括取込処理。"""

    def __init__(self) -> None:
        """呼出履歴を初期化する。"""

        self.calls: list[tuple[list[str], list[date]]] = []

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
        """日付件数に応じた固定結果を返す。"""

        del interval_minutes
        del data_source
        del continue_on_error
        del progress_callback

        self.calls.append((codes, target_dates))

        date_count = len(target_dates)

        return create_successful_batch_result(
            code_count=len(codes),
            date_count=date_count,
        )


class PartiallyFailingBatchImporter:
    """1営業日を失敗として返す一括取込処理。"""

    def __init__(self) -> None:
        """呼出回数を初期化する。"""

        self.call_count = 0

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
        """最初の日を失敗として返す。"""

        del interval_minutes
        del data_source
        del continue_on_error
        del progress_callback

        self.call_count += 1

        failed_date = target_dates[0]

        return JQuantsBatchImportResult(
            code_count=len(codes),
            date_count=len(target_dates),
            request_count=len(target_dates),
            successful_request_count=(
                len(target_dates) - 1
            ),
            empty_request_count=0,
            failed_request_count=1,
            minute_bar_count=300,
            five_minute_bar_count=60,
            processed_bar_count=60,
            failures=[
                JQuantsImportFailure(
                    code=codes[0],
                    target_date=failed_date,
                    message="test failure",
                )
            ],
        )


class RetryThenSuccessBatchImporter:
    """一時失敗後に成功する一括取込処理。"""

    def __init__(
        self,
        failure_count: int,
    ) -> None:
        """成功前に発生させる失敗回数を設定する。"""

        self.failure_count = failure_count
        self.call_count = 0

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
        """指定回数だけTimeoutErrorを発生させる。"""

        del interval_minutes
        del data_source
        del continue_on_error
        del progress_callback

        self.call_count += 1

        if self.call_count <= self.failure_count:
            raise TimeoutError(
                f"temporary failure {self.call_count}"
            )

        return create_successful_batch_result(
            code_count=len(codes),
            date_count=len(target_dates),
        )


class AlwaysFailingBatchImporter:
    """常に一時例外を送出する一括取込処理。"""

    def __init__(self) -> None:
        """呼出回数を初期化する。"""

        self.call_count = 0

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
        """常にTimeoutErrorを送出する。"""

        del codes
        del target_dates
        del interval_minutes
        del data_source
        del continue_on_error
        del progress_callback

        self.call_count += 1

        raise TimeoutError(
            f"permanent failure {self.call_count}"
        )


class NonRetryableFailingBatchImporter:
    """再試行対象外の例外を送出する一括取込処理。"""

    def __init__(self) -> None:
        """呼出回数を初期化する。"""

        self.call_count = 0

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
        """ValueErrorを送出する。"""

        del codes
        del target_dates
        del interval_minutes
        del data_source
        del continue_on_error
        del progress_callback

        self.call_count += 1

        raise ValueError("invalid response")


def create_successful_batch_result(
    *,
    code_count: int,
    date_count: int,
) -> JQuantsBatchImportResult:
    """成功した一括取込結果を作成する。"""

    return JQuantsBatchImportResult(
        code_count=code_count,
        date_count=date_count,
        request_count=date_count,
        successful_request_count=date_count,
        empty_request_count=0,
        failed_request_count=0,
        minute_bar_count=date_count * 300,
        five_minute_bar_count=date_count * 60,
        processed_bar_count=date_count * 60,
        failures=[],
    )


def create_business_dates(
    start_day: int,
    end_day: int,
) -> list[date]:
    """2026年7月の日付一覧を作成する。"""

    return [
        date(2026, 7, day)
        for day in range(
            start_day,
            end_day + 1,
        )
    ]


def create_state_repository(
    temporary_path: Path,
) -> HistoryStateRepository:
    """テスト用状態リポジトリを作成する。"""

    return HistoryStateRepository(
        temporary_path / "history_state.json"
    )


def test_create_date_range_includes_both_ends() -> None:
    """開始日と終了日を含む一覧を返す。"""

    result = create_date_range(
        date(2026, 7, 1),
        date(2026, 7, 3),
    )

    assert result == [
        date(2026, 7, 1),
        date(2026, 7, 2),
        date(2026, 7, 3),
    ]


def test_split_dates_creates_chunks() -> None:
    """日付一覧を指定件数で分割する。"""

    result = split_dates(
        create_business_dates(1, 5),
        chunk_size=2,
    )

    assert result == [
        [
            date(2026, 7, 1),
            date(2026, 7, 2),
        ],
        [
            date(2026, 7, 3),
            date(2026, 7, 4),
        ],
        [
            date(2026, 7, 5),
        ],
    ]


def test_filter_date_range_removes_outside_dates() -> None:
    """指定期間外の日付を除外する。"""

    result = filter_date_range(
        target_dates=create_business_dates(
            1,
            5,
        ),
        start_date=date(2026, 7, 2),
        end_date=date(2026, 7, 4),
    )

    assert result == [
        date(2026, 7, 2),
        date(2026, 7, 3),
        date(2026, 7, 4),
    ]


def test_history_importer_splits_business_dates() -> None:
    """営業日をチャンク分割して取り込む。"""

    calendar = FakeCalendarReader(
        create_business_dates(1, 5)
    )
    batch_importer = FakeBatchImporter()

    importer = JQuantsHistoryImporter(
        calendar_reader=calendar,
        batch_importer=batch_importer,
    )

    result = importer.run(
        codes=["7203"],
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 5),
        chunk_business_days=2,
    )

    assert len(batch_importer.calls) == 3

    assert batch_importer.calls[0] == (
        ["7203"],
        [
            date(2026, 7, 1),
            date(2026, 7, 2),
        ],
    )

    assert batch_importer.calls[2] == (
        ["7203"],
        [
            date(2026, 7, 5),
        ],
    )

    assert result.code_count == 1
    assert result.chunk_count == 3
    assert result.request_count == 5
    assert result.successful_request_count == 5
    assert result.minute_bar_count == 1500
    assert result.five_minute_bar_count == 300
    assert result.processed_bar_count == 300


def test_history_importer_processes_multiple_codes() -> None:
    """複数銘柄を個別にチャンク処理する。"""

    calendar = FakeCalendarReader(
        create_business_dates(1, 4)
    )
    batch_importer = FakeBatchImporter()

    result = JQuantsHistoryImporter(
        calendar_reader=calendar,
        batch_importer=batch_importer,
    ).run(
        codes=["7203", "8306"],
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 4),
        chunk_business_days=2,
    )

    assert result.code_count == 2
    assert result.chunk_count == 4
    assert result.request_count == 8
    assert len(batch_importer.calls) == 4


def test_history_importer_reports_progress() -> None:
    """チャンク完了ごとに進捗を通知する。"""

    calendar = FakeCalendarReader(
        create_business_dates(1, 5)
    )
    batch_importer = FakeBatchImporter()

    progress: list[HistoryImportProgress] = []

    JQuantsHistoryImporter(
        calendar_reader=calendar,
        batch_importer=batch_importer,
    ).run(
        codes=["7203"],
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 5),
        chunk_business_days=2,
        progress_callback=progress.append,
    )

    assert len(progress) == 3

    assert progress[0].completed_tasks == 1
    assert progress[0].total_tasks == 3
    assert progress[0].chunk_number == 1
    assert progress[0].completion_rate == (
        pytest.approx(100 / 3)
    )

    assert progress[-1].completed_tasks == 3
    assert progress[-1].completion_rate == (
        pytest.approx(100.0)
    )


def test_history_importer_collects_failures() -> None:
    """日別取得失敗を履歴取込結果へ引き継ぐ。"""

    calendar = FakeCalendarReader(
        create_business_dates(1, 2)
    )

    result = JQuantsHistoryImporter(
        calendar_reader=calendar,
        batch_importer=PartiallyFailingBatchImporter(),
    ).run(
        codes=["7203"],
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 2),
        chunk_business_days=2,
    )

    assert result.failed_request_count == 1
    assert result.failed_code_count == 1
    assert len(result.failures) == 1
    assert result.failures[0].code == "7203"
    assert result.failures[0].message == "test failure"


def test_history_importer_accepts_empty_calendar() -> None:
    """営業日が0件ならAPI取込せず正常終了する。"""

    calendar = FakeCalendarReader([])
    batch_importer = FakeBatchImporter()

    result = JQuantsHistoryImporter(
        calendar_reader=calendar,
        batch_importer=batch_importer,
    ).run(
        codes=["7203"],
        start_date=date(2026, 7, 11),
        end_date=date(2026, 7, 12),
    )

    assert batch_importer.calls == []
    assert result.code_count == 1
    assert result.chunk_count == 0
    assert result.request_count == 0
    assert result.processed_bar_count == 0


def test_history_importer_removes_duplicate_codes() -> None:
    """重複した銘柄コードを1回だけ処理する。"""

    calendar = FakeCalendarReader(
        create_business_dates(1, 1)
    )
    batch_importer = FakeBatchImporter()

    result = JQuantsHistoryImporter(
        calendar_reader=calendar,
        batch_importer=batch_importer,
    ).run(
        codes=["7203", "7203"],
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 1),
    )

    assert result.code_count == 1
    assert len(batch_importer.calls) == 1


def test_history_importer_saves_completed_chunk_state(
    tmp_path: Path,
) -> None:
    """成功したチャンクを完了状態として保存する。"""

    repository = create_state_repository(tmp_path)
    batch_importer = FakeBatchImporter()

    JQuantsHistoryImporter(
        calendar_reader=FakeCalendarReader(
            create_business_dates(1, 2)
        ),
        batch_importer=batch_importer,
        state_repository=repository,
    ).run(
        codes=["7203"],
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 2),
        chunk_business_days=2,
    )

    state = repository.load()

    key = HistoryTaskKey(
        code="7203",
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 2),
    )

    assert state.is_completed(key)
    assert state.failures == ()
    assert len(batch_importer.calls) == 1


def test_history_importer_skips_completed_chunk(
    tmp_path: Path,
) -> None:
    """保存済みの完了チャンクを再取得しない。"""

    repository = create_state_repository(tmp_path)

    key = HistoryTaskKey(
        code="7203",
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 2),
    )

    repository.save(
        HistoryImportState.empty().mark_completed(key)
    )

    batch_importer = FakeBatchImporter()
    progress: list[HistoryImportProgress] = []

    result = JQuantsHistoryImporter(
        calendar_reader=FakeCalendarReader(
            create_business_dates(1, 2)
        ),
        batch_importer=batch_importer,
        state_repository=repository,
    ).run(
        codes=["7203"],
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 2),
        chunk_business_days=2,
        progress_callback=progress.append,
    )

    assert batch_importer.calls == []
    assert result.request_count == 0
    assert result.failed_request_count == 0

    assert len(progress) == 1
    assert progress[0].completed_tasks == 1
    assert progress[0].total_tasks == 1
    assert progress[0].request_count == 0


def test_history_importer_resumes_only_unfinished_chunks(
    tmp_path: Path,
) -> None:
    """再開時は未完了チャンクだけを取り込む。"""

    repository = create_state_repository(tmp_path)

    completed_key = HistoryTaskKey(
        code="7203",
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 2),
    )

    repository.save(
        HistoryImportState.empty().mark_completed(
            completed_key
        )
    )

    batch_importer = FakeBatchImporter()

    JQuantsHistoryImporter(
        calendar_reader=FakeCalendarReader(
            create_business_dates(1, 4)
        ),
        batch_importer=batch_importer,
        state_repository=repository,
    ).run(
        codes=["7203"],
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 4),
        chunk_business_days=2,
    )

    assert batch_importer.calls == [
        (
            ["7203"],
            [
                date(2026, 7, 3),
                date(2026, 7, 4),
            ],
        )
    ]

    state = repository.load()

    second_key = HistoryTaskKey(
        code="7203",
        start_date=date(2026, 7, 3),
        end_date=date(2026, 7, 4),
    )

    assert state.is_completed(completed_key)
    assert state.is_completed(second_key)


def test_history_importer_retries_temporary_failure(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """一時的な例外を再試行し、成功後に完了保存する。"""

    repository = create_state_repository(tmp_path)
    batch_importer = RetryThenSuccessBatchImporter(
        failure_count=2
    )
    sleep_calls: list[float] = []

    caplog.set_level(
        logging.WARNING,
        logger="app.market.jquants_history_importer",
    )

    result = JQuantsHistoryImporter(
        calendar_reader=FakeCalendarReader(
            create_business_dates(1, 1)
        ),
        batch_importer=batch_importer,
        state_repository=repository,
        retry_policy=RetryPolicy(
            max_attempts=3,
            initial_delay_seconds=1.0,
            backoff_multiplier=2.0,
            maximum_delay_seconds=10.0,
        ),
        retry_sleeper=sleep_calls.append,
    ).run(
        codes=["7203"],
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 1),
    )

    assert batch_importer.call_count == 3
    assert sleep_calls == [1.0, 2.0]
    assert result.failed_request_count == 0

    key = HistoryTaskKey(
        code="7203",
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 1),
    )

    state = repository.load()

    assert state.is_completed(key)
    assert state.failures == ()

    retry_records = [
        record
        for record in caplog.records
        if "再試行します" in record.getMessage()
    ]

    assert len(retry_records) == 2
    assert "attempt_number=1" in retry_records[0].getMessage()
    assert "attempt_number=2" in retry_records[1].getMessage()


def test_history_importer_saves_failure_after_retry_exhausted(
    tmp_path: Path,
) -> None:
    """再試行上限後に失敗状態を保存する。"""

    repository = create_state_repository(tmp_path)
    batch_importer = AlwaysFailingBatchImporter()
    sleep_calls: list[float] = []

    result = JQuantsHistoryImporter(
        calendar_reader=FakeCalendarReader(
            create_business_dates(1, 1)
        ),
        batch_importer=batch_importer,
        state_repository=repository,
        retry_policy=RetryPolicy(
            max_attempts=3,
            initial_delay_seconds=0.5,
            backoff_multiplier=2.0,
            maximum_delay_seconds=5.0,
        ),
        retry_sleeper=sleep_calls.append,
    ).run(
        codes=["7203"],
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 1),
        continue_on_error=True,
    )

    assert batch_importer.call_count == 3
    assert sleep_calls == [0.5, 1.0]
    assert result.failed_request_count == 1
    assert len(result.failures) == 1
    assert result.failures[0].message == "permanent failure 3"

    state = repository.load()

    assert len(state.failures) == 1
    assert state.failures[0].attempt_count == 3
    assert state.failures[0].message == "permanent failure 3"


def test_history_importer_raises_after_saving_failure(
    tmp_path: Path,
) -> None:
    """処理継続無効時は失敗保存後に例外を送出する。"""

    repository = create_state_repository(tmp_path)
    batch_importer = AlwaysFailingBatchImporter()

    importer = JQuantsHistoryImporter(
        calendar_reader=FakeCalendarReader(
            create_business_dates(1, 1)
        ),
        batch_importer=batch_importer,
        state_repository=repository,
        retry_policy=RetryPolicy(
            max_attempts=2,
            initial_delay_seconds=0.0,
            backoff_multiplier=1.0,
            maximum_delay_seconds=0.0,
        ),
        retry_sleeper=lambda _: None,
    )

    with pytest.raises(RetryExhaustedError):
        importer.run(
            codes=["7203"],
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 1),
            continue_on_error=False,
        )

    state = repository.load()

    assert len(state.failures) == 1
    assert state.failures[0].attempt_count == 2
    assert state.failures[0].message == "permanent failure 2"


def test_history_importer_saves_partial_failure_state(
    tmp_path: Path,
) -> None:
    """部分失敗したチャンクを完了扱いにしない。"""

    repository = create_state_repository(tmp_path)
    batch_importer = PartiallyFailingBatchImporter()

    JQuantsHistoryImporter(
        calendar_reader=FakeCalendarReader(
            create_business_dates(1, 2)
        ),
        batch_importer=batch_importer,
        state_repository=repository,
    ).run(
        codes=["7203"],
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 2),
        chunk_business_days=2,
    )

    key = HistoryTaskKey(
        code="7203",
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 2),
    )

    state = repository.load()

    assert not state.is_completed(key)
    assert len(state.failures) == 1
    assert state.failures[0].attempt_count == 1
    assert "test failure" in state.failures[0].message


def test_history_importer_retries_failed_chunk_on_resume(
    tmp_path: Path,
) -> None:
    """失敗状態のチャンクは再開時に再実行する。"""

    repository = create_state_repository(tmp_path)
    failing_importer = PartiallyFailingBatchImporter()

    first_result = JQuantsHistoryImporter(
        calendar_reader=FakeCalendarReader(
            create_business_dates(1, 2)
        ),
        batch_importer=failing_importer,
        state_repository=repository,
    ).run(
        codes=["7203"],
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 2),
        chunk_business_days=2,
    )

    assert first_result.failed_request_count == 1
    assert failing_importer.call_count == 1

    successful_importer = FakeBatchImporter()

    second_result = JQuantsHistoryImporter(
        calendar_reader=FakeCalendarReader(
            create_business_dates(1, 2)
        ),
        batch_importer=successful_importer,
        state_repository=repository,
    ).run(
        codes=["7203"],
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 2),
        chunk_business_days=2,
    )

    assert len(successful_importer.calls) == 1
    assert second_result.failed_request_count == 0

    state = repository.load()

    key = HistoryTaskKey(
        code="7203",
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 2),
    )

    assert state.is_completed(key)
    assert state.failures == ()


def test_history_importer_handles_non_retryable_failure(
    tmp_path: Path,
) -> None:
    """再試行対象外の例外を1回で失敗保存する。"""

    repository = create_state_repository(tmp_path)
    batch_importer = NonRetryableFailingBatchImporter()

    result = JQuantsHistoryImporter(
        calendar_reader=FakeCalendarReader(
            create_business_dates(1, 1)
        ),
        batch_importer=batch_importer,
        state_repository=repository,
        retry_policy=RetryPolicy(
            max_attempts=5,
            initial_delay_seconds=0.0,
            backoff_multiplier=1.0,
            maximum_delay_seconds=0.0,
        ),
        retry_exceptions=(TimeoutError,),
        retry_sleeper=lambda _: None,
    ).run(
        codes=["7203"],
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 1),
        continue_on_error=True,
    )

    assert batch_importer.call_count == 1
    assert result.failed_request_count == 1
    assert result.failures[0].message == "invalid response"

    state = repository.load()

    assert len(state.failures) == 1
    assert state.failures[0].attempt_count == 1
    assert state.failures[0].message == "invalid response"


def test_history_importer_rejects_empty_retry_exceptions() -> None:
    """再試行対象例外が空なら初期化を拒否する。"""

    with pytest.raises(
        ValueError,
        match="再試行対象",
    ):
        JQuantsHistoryImporter(
            calendar_reader=FakeCalendarReader([]),
            batch_importer=FakeBatchImporter(),
            retry_exceptions=(),
        )


@pytest.mark.parametrize(
    (
        "codes",
        "start_date",
        "end_date",
        "chunk_business_days",
        "message",
    ),
    [
        (
            [],
            date(2026, 7, 1),
            date(2026, 7, 5),
            20,
            "銘柄コード",
        ),
        (
            ["ABCD"],
            date(2026, 7, 1),
            date(2026, 7, 5),
            20,
            "数字",
        ),
        (
            ["7203"],
            date(2026, 7, 5),
            date(2026, 7, 1),
            20,
            "開始日",
        ),
        (
            ["7203"],
            date(2026, 7, 1),
            date(2026, 7, 5),
            0,
            "チャンク営業日数",
        ),
    ],
)
def test_history_importer_rejects_invalid_arguments(
    codes: list[str],
    start_date: date,
    end_date: date,
    chunk_business_days: int,
    message: str,
) -> None:
    """不正な履歴取込条件を拒否する。"""

    importer = JQuantsHistoryImporter(
        calendar_reader=FakeCalendarReader([]),
        batch_importer=FakeBatchImporter(),
    )

    with pytest.raises(
        ValueError,
        match=message,
    ):
        importer.run(
            codes=codes,
            start_date=start_date,
            end_date=end_date,
            chunk_business_days=chunk_business_days,
        )