"""J-Quants定期差分更新CLIのテスト。"""

from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from app.update_jquants_history import (
    EXIT_PARTIAL_FAILURE,
    EXIT_SUCCESS,
    ScheduledUpdateResult,
    determine_exit_code,
    merge_history_results,
    parse_arguments,
    resolve_target_end_date,
    run_incremental_update,
    run_locked_incremental_update,
)
from app.market.history_progress import (
    HistoryImportFailure,
    HistoryImportResult,
    HistorySymbolResult,
)
from app.market.history_retry import (
    RetryPolicy,
)
from app.market.history_state import (
    HistoryStateRepository,
)
from app.market.jquants_batch_import import (
    JQuantsBatchImportResult,
    JQuantsImportFailure,
)
from app.market.process_lock import (
    AlreadyLockedError,
    ProcessLock,
)


class FakeRepository:
    """テスト用の最新時間足Repository。"""

    def __init__(
        self,
        latest_by_code: dict[
            str,
            datetime | None,
        ],
    ) -> None:
        """銘柄別の最新保存日時を設定する。"""

        self.latest_by_code = latest_by_code
        self.calls: list[
            tuple[str, int]
        ] = []

    def latest_datetime(
        self,
        code: str,
        interval_minutes: int,
    ) -> datetime | None:
        """設定済みの最新保存日時を返す。"""

        self.calls.append(
            (
                code,
                interval_minutes,
            )
        )

        return self.latest_by_code.get(
            code
        )


class FakeCalendarReader:
    """テスト用の取引カレンダー。"""

    def __init__(
        self,
        business_dates: list[date],
    ) -> None:
        """返却する営業日を設定する。"""

        self.business_dates = business_dates
        self.calls: list[
            tuple[date, date]
        ] = []

    def get_business_dates(
        self,
        start_date: date,
        end_date: date,
    ) -> list[date]:
        """指定範囲内の営業日だけを返す。"""

        self.calls.append(
            (
                start_date,
                end_date,
            )
        )

        return [
            business_date
            for business_date in self.business_dates
            if (
                start_date
                <= business_date
                <= end_date
            )
        ]


class FakeBatchImporter:
    """成功結果を返すテスト用一括取込処理。"""

    def __init__(self) -> None:
        """呼出履歴を初期化する。"""

        self.calls: list[
            tuple[list[str], list[date]]
        ] = []

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
        """日付件数に応じた成功結果を返す。"""

        del interval_minutes
        del data_source
        del continue_on_error
        del progress_callback

        self.calls.append(
            (
                codes,
                target_dates,
            )
        )

        date_count = len(
            target_dates
        )

        return JQuantsBatchImportResult(
            code_count=len(codes),
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


class PartiallyFailingBatchImporter:
    """1件の失敗を含む結果を返す一括取込処理。"""

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
        """最初の営業日を失敗として返す。"""

        del interval_minutes
        del data_source
        del continue_on_error
        del progress_callback

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
            minute_bar_count=0,
            five_minute_bar_count=0,
            processed_bar_count=0,
            failures=[
                JQuantsImportFailure(
                    code=codes[0],
                    target_date=failed_date,
                    message="test failure",
                )
            ],
        )


def create_process_lock(
    lock_path: Path,
    *,
    lock_id: str,
) -> ProcessLock:
    """固定値を使うテスト用プロセスロックを作成する。"""

    return ProcessLock(
        file_path=lock_path,
        process_name="scheduled-update-test",
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


def create_symbol_result(
    code: str,
    *,
    failed_request_count: int = 0,
) -> HistorySymbolResult:
    """集約テスト用銘柄結果を作成する。"""

    return HistorySymbolResult(
        code=code,
        business_date_count=1,
        chunk_count=1,
        request_count=1,
        successful_request_count=(
            0
            if failed_request_count
            else 1
        ),
        empty_request_count=0,
        failed_request_count=(
            failed_request_count
        ),
        minute_bar_count=(
            0
            if failed_request_count
            else 300
        ),
        five_minute_bar_count=(
            0
            if failed_request_count
            else 60
        ),
        processed_bar_count=(
            0
            if failed_request_count
            else 60
        ),
    )


def test_parse_arguments_reads_scheduled_update_options(
    tmp_path: Path,
) -> None:
    """定期更新用のCLI引数を読み込む。"""

    state_path = (
        tmp_path / "state.json"
    )
    report_path = (
        tmp_path / "report.csv"
    )
    lock_path = (
        tmp_path / "update.lock"
    )

    arguments = parse_arguments(
        [
            "--codes",
            "7203",
            "8306",
            "--initial-start-date",
            "2026-01-01",
            "--target-end-date",
            "2026-07-15",
            "--state-file",
            str(state_path),
            "--report-csv",
            str(report_path),
            "--lock-file",
            str(lock_path),
            "--lock-stale-seconds",
            "1800",
            "--reset-state",
            "--stop-on-error",
        ]
    )

    assert arguments.codes == [
        "7203",
        "8306",
    ]
    assert arguments.initial_start_date == (
        "2026-01-01"
    )
    assert arguments.target_end_date == (
        "2026-07-15"
    )
    assert arguments.state_file == state_path
    assert arguments.report_csv == report_path
    assert arguments.lock_file == lock_path
    assert arguments.lock_stale_seconds == 1800
    assert arguments.reset_state is True
    assert arguments.stop_on_error is True


def test_resolve_target_end_date_uses_argument() -> None:
    """指定された更新終了日を使用する。"""

    assert resolve_target_end_date(
        "2026-07-15",
        today=date(2026, 7, 16),
    ) == date(
        2026,
        7,
        15,
    )


def test_resolve_target_end_date_uses_today() -> None:
    """終了日省略時は実行日を使用する。"""

    assert resolve_target_end_date(
        None,
        today=date(2026, 7, 16),
    ) == date(
        2026,
        7,
        16,
    )


def test_incremental_update_processes_only_missing_ranges(
    tmp_path: Path,
) -> None:
    """銘柄ごとの未取得期間だけを履歴取込する。"""

    repository = FakeRepository(
        {
            "7203": datetime(
                2026,
                7,
                2,
                15,
                0,
            ),
            "8306": datetime(
                2026,
                7,
                4,
                15,
                0,
            ),
        }
    )

    calendar = FakeCalendarReader(
        [
            date(2026, 7, 1),
            date(2026, 7, 2),
            date(2026, 7, 3),
            date(2026, 7, 4),
            date(2026, 7, 5),
        ]
    )

    batch_importer = FakeBatchImporter()

    result = run_incremental_update(
        codes=["7203", "8306"],
        initial_start_date=date(2026, 7, 1),
        target_end_date=date(2026, 7, 5),
        chunk_business_days=20,
        request_interval_seconds=0,
        continue_on_error=True,
        repository=repository,
        calendar_reader=calendar,
        state_repository=HistoryStateRepository(
            tmp_path / "state.json"
        ),
        retry_policy=RetryPolicy(
            max_attempts=1,
            initial_delay_seconds=0,
            backoff_multiplier=1,
            maximum_delay_seconds=0,
        ),
        batch_importer=batch_importer,
        retry_sleeper=lambda _: None,
        today=date(2026, 7, 16),
    )

    assert result.plan.update_code_count == 2
    assert result.plan.skipped_code_count == 0

    assert batch_importer.calls == [
        (
            ["7203"],
            [
                date(2026, 7, 3),
                date(2026, 7, 4),
                date(2026, 7, 5),
            ],
        ),
        (
            ["8306"],
            [
                date(2026, 7, 5),
            ],
        ),
    ]

    assert result.history_result.code_count == 2
    assert result.history_result.request_count == 4
    assert result.history_result.failed_request_count == 0


def test_incremental_update_skips_up_to_date_symbol(
    tmp_path: Path,
) -> None:
    """最新状態の銘柄では取込処理を呼び出さない。"""

    batch_importer = FakeBatchImporter()

    result = run_incremental_update(
        codes=["7203"],
        initial_start_date=date(2026, 7, 1),
        target_end_date=date(2026, 7, 5),
        chunk_business_days=20,
        request_interval_seconds=0,
        continue_on_error=True,
        repository=FakeRepository(
            {
                "7203": datetime(
                    2026,
                    7,
                    5,
                    15,
                    0,
                ),
            }
        ),
        calendar_reader=FakeCalendarReader([]),
        state_repository=HistoryStateRepository(
            tmp_path / "state.json"
        ),
        batch_importer=batch_importer,
        today=date(2026, 7, 16),
    )

    assert result.plan.update_code_count == 0
    assert result.plan.skipped_code_count == 1
    assert result.plan.is_up_to_date is True
    assert batch_importer.calls == []

    assert result.history_result.code_count == 1
    assert result.history_result.request_count == 0
    assert result.history_result.processed_bar_count == 0


def test_incremental_update_writes_csv_report(
    tmp_path: Path,
) -> None:
    """差分更新結果をCSVへ保存する。"""

    report_path = (
        tmp_path / "reports" / "update.csv"
    )

    result = run_incremental_update(
        codes=["7203"],
        initial_start_date=date(2026, 7, 1),
        target_end_date=date(2026, 7, 1),
        chunk_business_days=20,
        request_interval_seconds=0,
        continue_on_error=True,
        repository=FakeRepository(
            {
                "7203": None,
            }
        ),
        calendar_reader=FakeCalendarReader(
            [
                date(2026, 7, 1),
            ]
        ),
        state_repository=HistoryStateRepository(
            tmp_path / "state.json"
        ),
        batch_importer=FakeBatchImporter(),
        report_path=report_path,
        today=date(2026, 7, 16),
    )

    assert result.report_path == report_path
    assert report_path.exists()

    report_text = report_path.read_text(
        encoding="utf-8-sig"
    )

    assert "record_type" in report_text
    assert "summary" in report_text
    assert "symbol" in report_text
    assert "7203" in report_text


def test_incremental_update_preserves_partial_failure(
    tmp_path: Path,
) -> None:
    """部分失敗を統合結果へ引き継ぐ。"""

    result = run_incremental_update(
        codes=["7203"],
        initial_start_date=date(2026, 7, 1),
        target_end_date=date(2026, 7, 1),
        chunk_business_days=20,
        request_interval_seconds=0,
        continue_on_error=True,
        repository=FakeRepository(
            {
                "7203": None,
            }
        ),
        calendar_reader=FakeCalendarReader(
            [
                date(2026, 7, 1),
            ]
        ),
        state_repository=HistoryStateRepository(
            tmp_path / "state.json"
        ),
        batch_importer=(
            PartiallyFailingBatchImporter()
        ),
        today=date(2026, 7, 16),
    )

    assert result.failed_request_count == 1
    assert len(
        result.history_result.failures
    ) == 1
    assert (
        result.history_result.failures[0].message
        == "test failure"
    )

    assert determine_exit_code(
        result
    ) == EXIT_PARTIAL_FAILURE


def test_locked_update_releases_lock_after_success(
    tmp_path: Path,
) -> None:
    """正常終了後にプロセスロックを削除する。"""

    lock_path = (
        tmp_path / "update.lock"
    )

    result = run_locked_incremental_update(
        process_lock=create_process_lock(
            lock_path,
            lock_id="success-lock",
        ),
        codes=["7203"],
        initial_start_date=date(2026, 7, 1),
        target_end_date=date(2026, 7, 1),
        chunk_business_days=20,
        request_interval_seconds=0,
        continue_on_error=True,
        repository=FakeRepository(
            {
                "7203": None,
            }
        ),
        calendar_reader=FakeCalendarReader(
            [
                date(2026, 7, 1),
            ]
        ),
        state_repository=HistoryStateRepository(
            tmp_path / "state.json"
        ),
        batch_importer=FakeBatchImporter(),
        today=date(2026, 7, 16),
    )

    assert result.is_successful is True
    assert lock_path.exists() is False


def test_locked_update_rejects_second_execution(
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

    with pytest.raises(
        AlreadyLockedError,
    ):
        run_locked_incremental_update(
            process_lock=second_lock,
            codes=["7203"],
            initial_start_date=date(2026, 7, 1),
            target_end_date=date(2026, 7, 1),
            chunk_business_days=20,
            request_interval_seconds=0,
            continue_on_error=True,
            repository=FakeRepository(
                {
                    "7203": None,
                }
            ),
            calendar_reader=FakeCalendarReader(
                [
                    date(2026, 7, 1),
                ]
            ),
            state_repository=HistoryStateRepository(
                tmp_path / "state.json"
            ),
            batch_importer=FakeBatchImporter(),
            today=date(2026, 7, 16),
        )

    first_lock.release()


def test_merge_history_results_preserves_plan_order() -> None:
    """統合結果の銘柄順を差分計画の順序に合わせる。"""

    repository = FakeRepository(
        {
            "7203": None,
            "8306": datetime(
                2026,
                7,
                1,
                15,
                0,
            ),
        }
    )

    calendar = FakeCalendarReader(
        [
            date(2026, 7, 1),
        ]
    )

    from app.market.incremental_update import (
        IncrementalUpdatePlanner,
    )

    plan = IncrementalUpdatePlanner(
        repository=repository,
        calendar_reader=calendar,
    ).create_plan(
        codes=[
            "7203",
            "8306",
        ],
        initial_start_date=date(2026, 7, 1),
        target_end_date=date(2026, 7, 1),
        today=date(2026, 7, 16),
    )

    imported_result = HistoryImportResult(
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 1),
        code_results=[
            create_symbol_result("7203")
        ],
        failures=[],
    )

    merged = merge_history_results(
        plan=plan,
        imported_results=[
            imported_result
        ],
    )

    assert [
        result.code
        for result in merged.code_results
    ] == [
        "7203",
        "8306",
    ]

    assert merged.code_results[
        0
    ].request_count == 1

    assert merged.code_results[
        1
    ].request_count == 0


def test_determine_exit_code_returns_success() -> None:
    """失敗がなければ正常終了コードを返す。"""

    repository = FakeRepository(
        {
            "7203": None,
        }
    )
    calendar = FakeCalendarReader(
        [
            date(2026, 7, 1),
        ]
    )

    from app.market.incremental_update import (
        IncrementalUpdatePlanner,
    )

    plan = IncrementalUpdatePlanner(
        repository=repository,
        calendar_reader=calendar,
    ).create_plan(
        codes=["7203"],
        initial_start_date=date(2026, 7, 1),
        target_end_date=date(2026, 7, 1),
        today=date(2026, 7, 16),
    )

    history_result = HistoryImportResult(
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 1),
        code_results=[
            create_symbol_result("7203")
        ],
        failures=[],
    )

    result = ScheduledUpdateResult(
        plan=plan,
        history_result=history_result,
        report_path=None,
    )

    assert determine_exit_code(
        result
    ) == EXIT_SUCCESS