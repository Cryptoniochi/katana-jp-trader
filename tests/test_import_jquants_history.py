"""J-Quants履歴取込CLIのテスト。"""

import csv
import logging
from datetime import date
from pathlib import Path

import pytest

from app.import_jquants_history import (
    CSV_FIELD_NAMES,
    create_csv_rows,
    create_retry_policy,
    format_progress_message,
    parse_arguments,
    parse_date,
    resolve_codes,
    run_history_import,
    write_csv_report,
)
from app.market.history_progress import (
    HistoryImportFailure,
    HistoryImportProgress,
    HistoryImportResult,
    HistorySymbolResult,
)
from app.market.history_retry import (
    RetryPolicy,
)
from app.market.history_state import (
    HistoryStateRepository,
    HistoryTaskKey,
)
from app.market.jquants_batch_import import (
    JQuantsBatchImportResult,
)


class FakeCalendarReader:
    """テスト用の営業日取得処理。"""

    def __init__(
        self,
        business_dates: list[date],
    ) -> None:
        """返却する営業日を設定する。"""

        self.business_dates = business_dates

    def get_business_dates(
        self,
        start_date: date,
        end_date: date,
    ) -> list[date]:
        """設定済み営業日を返す。"""

        del start_date
        del end_date

        return self.business_dates


class FakeBatchImporter:
    """テスト用の履歴一括取込処理。"""

    def __init__(self) -> None:
        """呼び出し履歴を初期化する。"""

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
        """固定の成功結果を返す。"""

        del interval_minutes
        del data_source
        del continue_on_error
        del progress_callback

        self.calls.append(
            (codes, target_dates)
        )

        date_count = len(target_dates)

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


class RetryThenSuccessBatchImporter:
    """一時失敗後に成功する履歴取込処理。"""

    def __init__(self) -> None:
        """呼び出し回数を初期化する。"""

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
        """1回目だけTimeoutErrorを発生させる。"""

        del interval_minutes
        del data_source
        del continue_on_error
        del progress_callback

        self.call_count += 1

        if self.call_count == 1:
            raise TimeoutError(
                "temporary failure"
            )

        date_count = len(target_dates)

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


def write_watchlist(
    tmp_path: Path,
    content: str,
) -> Path:
    """テスト用Watch Listを作成する。"""

    file_path = (
        tmp_path / "watchlist.txt"
    )

    file_path.write_text(
        content,
        encoding="utf-8",
    )

    return file_path


def create_result() -> HistoryImportResult:
    """CSVテスト用の履歴取込結果を作成する。"""

    symbol_result = HistorySymbolResult(
        code="7203",
        business_date_count=2,
        chunk_count=1,
        request_count=2,
        successful_request_count=1,
        empty_request_count=0,
        failed_request_count=1,
        minute_bar_count=300,
        five_minute_bar_count=60,
        processed_bar_count=60,
    )

    failure = HistoryImportFailure(
        code="7203",
        start_date=date(2026, 7, 2),
        end_date=date(2026, 7, 2),
        message="test failure",
    )

    return HistoryImportResult(
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 2),
        code_results=[symbol_result],
        failures=[failure],
    )


def test_parse_date_returns_date() -> None:
    """日付文字列をdateへ変換する。"""

    assert parse_date(
        "2026-07-15"
    ) == date(
        2026,
        7,
        15,
    )


def test_parse_date_rejects_invalid_format() -> None:
    """不正な日付形式を拒否する。"""

    with pytest.raises(
        ValueError,
        match="YYYY-MM-DD",
    ):
        parse_date(
            "2026/07/15"
        )


def test_resolve_codes_prefers_command_codes(
    tmp_path: Path,
) -> None:
    """コマンド指定銘柄をWatch Listより優先する。"""

    watchlist_path = write_watchlist(
        tmp_path,
        "7203\n8306\n",
    )

    codes, source = resolve_codes(
        command_codes=[
            "9984",
            "6758",
        ],
        watchlist_path=watchlist_path,
    )

    assert codes == [
        "9984",
        "6758",
    ]
    assert source == "command"


def test_resolve_codes_reads_watchlist(
    tmp_path: Path,
) -> None:
    """コマンド指定がなければWatch Listを読む。"""

    watchlist_path = write_watchlist(
        tmp_path,
        "7203\n8306\n",
    )

    codes, source = resolve_codes(
        command_codes=None,
        watchlist_path=watchlist_path,
    )

    assert codes == [
        "7203",
        "8306",
    ]
    assert source == str(
        watchlist_path
    )


def test_parse_arguments_reads_cli_extensions(
    tmp_path: Path,
) -> None:
    """状態、CSV、リトライのCLI引数を読み込む。"""

    state_path = (
        tmp_path / "state.json"
    )
    report_path = (
        tmp_path / "report.csv"
    )

    arguments = parse_arguments(
        [
            "--codes",
            "7203",
            "8306",
            "--state-file",
            str(state_path),
            "--report-csv",
            str(report_path),
            "--reset-state",
            "--retry-max-attempts",
            "5",
            "--retry-initial-delay",
            "0.5",
            "--retry-backoff",
            "1.5",
            "--retry-max-delay",
            "8.0",
            "--stop-on-error",
        ]
    )

    assert arguments.codes == [
        "7203",
        "8306",
    ]
    assert arguments.state_file == state_path
    assert arguments.report_csv == report_path
    assert arguments.reset_state is True
    assert arguments.retry_max_attempts == 5
    assert arguments.retry_initial_delay == 0.5
    assert arguments.retry_backoff == 1.5
    assert arguments.retry_max_delay == 8.0
    assert arguments.stop_on_error is True


def test_parse_arguments_accepts_no_report() -> None:
    """CSVレポート無効化引数を読み込む。"""

    arguments = parse_arguments(
        ["--no-report"]
    )

    assert arguments.no_report is True


def test_create_retry_policy() -> None:
    """CLI値から再試行条件を作成する。"""

    policy = create_retry_policy(
        max_attempts=4,
        initial_delay_seconds=0.25,
        backoff_multiplier=1.5,
        maximum_delay_seconds=5.0,
    )

    assert policy == RetryPolicy(
        max_attempts=4,
        initial_delay_seconds=0.25,
        backoff_multiplier=1.5,
        maximum_delay_seconds=5.0,
    )


def test_create_retry_policy_rejects_invalid_value() -> None:
    """不正な再試行条件を拒否する。"""

    with pytest.raises(
        ValueError,
        match="最大試行回数",
    ):
        create_retry_policy(
            max_attempts=0,
            initial_delay_seconds=1.0,
            backoff_multiplier=2.0,
            maximum_delay_seconds=30.0,
        )


def test_format_progress_message() -> None:
    """履歴取込の進捗文字列を作成する。"""

    progress = HistoryImportProgress(
        completed_tasks=1,
        total_tasks=4,
        code="7203",
        chunk_number=1,
        chunk_count=2,
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 2),
        request_count=2,
        successful_request_count=2,
        empty_request_count=0,
        failed_request_count=0,
        minute_bar_count=600,
        five_minute_bar_count=120,
        processed_bar_count=120,
    )

    message = format_progress_message(
        progress
    )

    assert "1/4" in message
    assert "25.0%" in message
    assert "code=7203" in message
    assert "chunk=1/2" in message
    assert "processed=120" in message


def test_run_history_import_connects_services() -> None:
    """営業日取得処理と一括取込処理を接続する。"""

    calendar = FakeCalendarReader(
        [
            date(2026, 7, 1),
            date(2026, 7, 2),
            date(2026, 7, 3),
        ]
    )
    batch_importer = FakeBatchImporter()

    progress: list[
        HistoryImportProgress
    ] = []

    result = run_history_import(
        codes=["7203", "8306"],
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 3),
        chunk_business_days=2,
        request_interval_seconds=0,
        continue_on_error=True,
        calendar_reader=calendar,
        batch_importer=batch_importer,
        progress_callback=progress.append,
    )

    assert result.code_count == 2
    assert result.chunk_count == 4
    assert result.request_count == 6
    assert result.processed_bar_count == 360

    assert batch_importer.calls == [
        (
            ["7203"],
            [
                date(2026, 7, 1),
                date(2026, 7, 2),
            ],
        ),
        (
            ["7203"],
            [
                date(2026, 7, 3),
            ],
        ),
        (
            ["8306"],
            [
                date(2026, 7, 1),
                date(2026, 7, 2),
            ],
        ),
        (
            ["8306"],
            [
                date(2026, 7, 3),
            ],
        ),
    ]

    assert len(progress) == 4
    assert progress[-1].completion_rate == (
        pytest.approx(100.0)
    )


def test_run_history_import_uses_state_file(
    tmp_path: Path,
) -> None:
    """状態ファイルを使って完了チャンクを保存する。"""

    state_path = (
        tmp_path / "state.json"
    )
    batch_importer = FakeBatchImporter()

    run_history_import(
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
        batch_importer=batch_importer,
    )

    repository = HistoryStateRepository(
        state_path
    )
    state = repository.load()

    key = HistoryTaskKey(
        code="7203",
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 2),
    )

    assert state.is_completed(key)
    assert len(batch_importer.calls) == 1


def test_run_history_import_resumes_from_state_file(
    tmp_path: Path,
) -> None:
    """再実行時に完了済みチャンクをスキップする。"""

    state_path = (
        tmp_path / "state.json"
    )

    first_importer = FakeBatchImporter()

    run_history_import(
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
        batch_importer=first_importer,
    )

    second_importer = FakeBatchImporter()

    result = run_history_import(
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
        batch_importer=second_importer,
    )

    assert len(first_importer.calls) == 1
    assert second_importer.calls == []
    assert result.request_count == 0


def test_run_history_import_uses_retry_policy() -> None:
    """指定された再試行条件を履歴取込へ渡す。"""

    batch_importer = (
        RetryThenSuccessBatchImporter()
    )
    sleep_calls: list[float] = []

    result = run_history_import(
        codes=["7203"],
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 1),
        chunk_business_days=1,
        request_interval_seconds=0,
        continue_on_error=True,
        retry_policy=RetryPolicy(
            max_attempts=2,
            initial_delay_seconds=0.25,
            backoff_multiplier=2.0,
            maximum_delay_seconds=1.0,
        ),
        retry_sleeper=sleep_calls.append,
        calendar_reader=FakeCalendarReader(
            [date(2026, 7, 1)]
        ),
        batch_importer=batch_importer,
    )

    assert batch_importer.call_count == 2
    assert sleep_calls == [0.25]
    assert result.failed_request_count == 0


def test_run_history_import_rejects_negative_interval() -> None:
    """負のリクエスト間隔を拒否する。"""

    with pytest.raises(
        ValueError,
        match="リクエスト間隔",
    ):
        run_history_import(
            codes=["7203"],
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 1),
            chunk_business_days=20,
            request_interval_seconds=-1,
            continue_on_error=True,
            calendar_reader=FakeCalendarReader(
                []
            ),
            batch_importer=FakeBatchImporter(),
        )


def test_create_csv_rows_contains_all_record_types() -> None:
    """集計・銘柄・失敗のCSV行を作成する。"""

    rows = create_csv_rows(
        create_result()
    )

    assert len(rows) == 3
    assert rows[0]["record_type"] == "summary"
    assert rows[1]["record_type"] == "symbol"
    assert rows[2]["record_type"] == "failure"

    assert rows[1]["code"] == "7203"
    assert rows[2]["message"] == (
        "test failure"
    )


def test_write_csv_report(
    tmp_path: Path,
) -> None:
    """履歴取込結果をCSVへ保存する。"""

    output_path = (
        tmp_path
        / "reports"
        / "history.csv"
    )

    saved_path = write_csv_report(
        result=create_result(),
        output_path=output_path,
    )

    assert saved_path == output_path
    assert output_path.exists()

    with output_path.open(
        mode="r",
        encoding="utf-8-sig",
        newline="",
    ) as csv_file:
        rows = list(
            csv.DictReader(csv_file)
        )

    assert len(rows) == 3
    assert list(rows[0].keys()) == (
        CSV_FIELD_NAMES
    )

    assert rows[0]["record_type"] == (
        "summary"
    )
    assert rows[1]["record_type"] == (
        "symbol"
    )
    assert rows[2]["record_type"] == (
        "failure"
    )

    assert rows[1]["code"] == "7203"
    assert rows[2]["start_date"] == (
        "2026-07-02"
    )
    assert rows[2]["message"] == (
        "test failure"
    )


def test_write_csv_report_replaces_existing_file(
    tmp_path: Path,
) -> None:
    """既存CSVを完成した新規レポートで置換する。"""

    output_path = (
        tmp_path / "history.csv"
    )

    output_path.write_text(
        "old content",
        encoding="utf-8",
    )

    write_csv_report(
        result=create_result(),
        output_path=output_path,
    )

    text = output_path.read_text(
        encoding="utf-8-sig"
    )

    assert "old content" not in text
    assert "record_type" in text
    assert "test failure" in text


def test_write_csv_report_rejects_directory(
    tmp_path: Path,
) -> None:
    """CSV出力先がディレクトリなら拒否する。"""

    output_path = (
        tmp_path / "report.csv"
    )
    output_path.mkdir()

    with pytest.raises(
        OSError,
        match="ファイルではありません",
    ):
        write_csv_report(
            result=create_result(),
            output_path=output_path,
        )


def test_progress_message_can_be_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """進捗文字列を通常のLoggerへ出力できる。"""

    logger = logging.getLogger(
        "test_history_progress"
    )

    progress = HistoryImportProgress(
        completed_tasks=1,
        total_tasks=1,
        code="7203",
        chunk_number=1,
        chunk_count=1,
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 1),
        request_count=1,
        successful_request_count=1,
        empty_request_count=0,
        failed_request_count=0,
        minute_bar_count=300,
        five_minute_bar_count=60,
        processed_bar_count=60,
    )

    with caplog.at_level(
        logging.INFO,
        logger=logger.name,
    ):
        logger.info(
            "%s",
            format_progress_message(
                progress
            ),
        )

    assert "code=7203" in caplog.text
    assert "100.0%" in caplog.text