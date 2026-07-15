"""J-Quants履歴データ取込基盤のテスト。"""

from datetime import date

import pytest

from app.market.date_range import (
    create_date_range,
    filter_date_range,
    split_dates,
)
from app.market.history_progress import (
    HistoryImportProgress,
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
    """1営業日を失敗として返す一括取込処理。"""

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

        failed_date = target_dates[0]

        return JQuantsBatchImportResult(
            code_count=len(codes),
            date_count=len(target_dates),
            request_count=len(target_dates),
            successful_request_count=(len(target_dates) - 1),
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

    calendar = FakeCalendarReader(create_business_dates(1, 5))
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

    calendar = FakeCalendarReader(create_business_dates(1, 4))
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

    calendar = FakeCalendarReader(create_business_dates(1, 5))
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
    assert progress[0].completion_rate == (pytest.approx(100 / 3))

    assert progress[-1].completed_tasks == 3
    assert progress[-1].completion_rate == (pytest.approx(100.0))


def test_history_importer_collects_failures() -> None:
    """日別取得失敗を履歴取込結果へ引き継ぐ。"""

    calendar = FakeCalendarReader(create_business_dates(1, 2))

    result = JQuantsHistoryImporter(
        calendar_reader=calendar,
        batch_importer=(PartiallyFailingBatchImporter()),
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
    assert result.failures[0].message == ("test failure")


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

    calendar = FakeCalendarReader(create_business_dates(1, 1))
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

    with pytest.raises(ValueError, match=message):
        importer.run(
            codes=codes,
            start_date=start_date,
            end_date=end_date,
            chunk_business_days=(chunk_business_days),
        )
