"""J-Quants履歴取込CLIのテスト。"""

import logging
from datetime import date
from pathlib import Path

import pytest

from app.import_jquants_history import (
    format_progress_message,
    parse_date,
    resolve_codes,
    run_history_import,
)
from app.market.history_progress import (
    HistoryImportProgress,
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
        """固定の成功結果を返す。"""

        del interval_minutes
        del data_source
        del continue_on_error
        del progress_callback

        self.calls.append((codes, target_dates))

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

    file_path = tmp_path / "watchlist.txt"

    file_path.write_text(
        content,
        encoding="utf-8",
    )

    return file_path


def test_parse_date_returns_date() -> None:
    """日付文字列をdateへ変換する。"""

    assert parse_date("2026-07-15") == date(
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
        parse_date("2026/07/15")


def test_resolve_codes_prefers_command_codes(
    tmp_path: Path,
) -> None:
    """コマンド指定銘柄をWatch Listより優先する。"""

    watchlist_path = write_watchlist(
        tmp_path,
        "7203\n8306\n",
    )

    codes, source = resolve_codes(
        command_codes=["9984", "6758"],
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
    assert source == str(watchlist_path)


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

    message = format_progress_message(progress)

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

    progress: list[HistoryImportProgress] = []

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
    assert progress[-1].completion_rate == (pytest.approx(100.0))


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
            calendar_reader=FakeCalendarReader([]),
            batch_importer=FakeBatchImporter(),
        )


def test_progress_message_can_be_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """進捗文字列を通常のLoggerへ出力できる。"""

    logger = logging.getLogger("test_history_progress")

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
            format_progress_message(progress),
        )

    assert "code=7203" in caplog.text
    assert "100.0%" in caplog.text
