"""市場時間足の差分更新範囲判定テスト。"""

from datetime import date, datetime

import pytest

from app.market.incremental_update import (
    IncrementalUpdateAction,
    IncrementalUpdatePlanner,
)


class FakeLatestMarketBarReader:
    """テスト用の最新時間足取得Repository。"""

    def __init__(
        self,
        latest_by_code: dict[str, datetime | None],
    ) -> None:
        """銘柄別の最新保存日時を設定する。"""

        self.latest_by_code = latest_by_code
        self.calls: list[tuple[str, int]] = []

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

        return self.latest_by_code.get(code)


class FakeTradingCalendarReader:
    """テスト用の取引カレンダー。"""

    def __init__(
        self,
        business_dates: list[date],
    ) -> None:
        """返却する営業日一覧を設定する。"""

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


def test_planner_uses_initial_start_for_new_symbol() -> None:
    """保存データがない銘柄は初回開始日から更新する。"""

    repository = FakeLatestMarketBarReader(
        {
            "7203": None,
        }
    )
    calendar = FakeTradingCalendarReader(
        [
            date(2026, 7, 1),
            date(2026, 7, 2),
            date(2026, 7, 3),
        ]
    )

    plan = IncrementalUpdatePlanner(
        repository=repository,
        calendar_reader=calendar,
    ).create_plan(
        codes=["7203"],
        initial_start_date=date(2026, 7, 1),
        target_end_date=date(2026, 7, 3),
        interval_minutes=5,
        today=date(2026, 7, 10),
    )

    assert plan.code_count == 1
    assert plan.update_code_count == 1
    assert plan.skipped_code_count == 0
    assert plan.total_business_date_count == 3
    assert plan.is_up_to_date is False

    task = plan.tasks[0]

    assert task.code == "7203"
    assert task.latest_saved_at is None
    assert task.requested_start_date == date(
        2026,
        7,
        1,
    )
    assert task.update_start_date == date(
        2026,
        7,
        1,
    )
    assert task.update_end_date == date(
        2026,
        7,
        3,
    )
    assert task.business_date_count == 3
    assert task.action is IncrementalUpdateAction.UPDATE
    assert task.should_update is True

    assert repository.calls == [
        (
            "7203",
            5,
        )
    ]

    assert calendar.calls == [
        (
            date(2026, 7, 1),
            date(2026, 7, 3),
        )
    ]


def test_planner_starts_after_latest_saved_date() -> None:
    """保存済み最終日の翌日から差分更新する。"""

    repository = FakeLatestMarketBarReader(
        {
            "7203": datetime(
                2026,
                7,
                2,
                15,
                0,
            ),
        }
    )
    calendar = FakeTradingCalendarReader(
        create_business_dates(
            3,
            6,
        )
    )

    plan = IncrementalUpdatePlanner(
        repository=repository,
        calendar_reader=calendar,
    ).create_plan(
        codes=["7203"],
        initial_start_date=date(2026, 7, 1),
        target_end_date=date(2026, 7, 6),
        interval_minutes=5,
        today=date(2026, 7, 10),
    )

    task = plan.tasks[0]

    assert task.requested_start_date == date(
        2026,
        7,
        3,
    )
    assert task.business_dates == (
        date(2026, 7, 3),
        date(2026, 7, 4),
        date(2026, 7, 5),
        date(2026, 7, 6),
    )
    assert task.action is IncrementalUpdateAction.UPDATE


def test_planner_skips_symbol_already_up_to_date() -> None:
    """最終保存日が終了日と同じなら更新不要にする。"""

    repository = FakeLatestMarketBarReader(
        {
            "7203": datetime(
                2026,
                7,
                5,
                15,
                0,
            ),
        }
    )
    calendar = FakeTradingCalendarReader([])

    plan = IncrementalUpdatePlanner(
        repository=repository,
        calendar_reader=calendar,
    ).create_plan(
        codes=["7203"],
        initial_start_date=date(2026, 7, 1),
        target_end_date=date(2026, 7, 5),
        interval_minutes=5,
        today=date(2026, 7, 10),
    )

    task = plan.tasks[0]

    assert task.requested_start_date == date(
        2026,
        7,
        6,
    )
    assert task.business_dates == ()
    assert task.update_start_date is None
    assert task.update_end_date is None
    assert task.action is (
        IncrementalUpdateAction.SKIP_UP_TO_DATE
    )
    assert task.should_update is False

    assert plan.update_code_count == 0
    assert plan.skipped_code_count == 1
    assert plan.is_up_to_date is True
    assert calendar.calls == []


def test_planner_skips_when_no_business_dates_exist() -> None:
    """対象期間に営業日がなければAPI更新を不要にする。"""

    repository = FakeLatestMarketBarReader(
        {
            "7203": None,
        }
    )
    calendar = FakeTradingCalendarReader([])

    plan = IncrementalUpdatePlanner(
        repository=repository,
        calendar_reader=calendar,
    ).create_plan(
        codes=["7203"],
        initial_start_date=date(2026, 7, 4),
        target_end_date=date(2026, 7, 5),
        interval_minutes=5,
        today=date(2026, 7, 10),
    )

    task = plan.tasks[0]

    assert task.action is (
        IncrementalUpdateAction.SKIP_NO_BUSINESS_DATES
    )
    assert task.should_update is False
    assert task.business_date_count == 0
    assert plan.is_up_to_date is True

    assert calendar.calls == [
        (
            date(2026, 7, 4),
            date(2026, 7, 5),
        )
    ]


def test_planner_creates_different_ranges_for_each_code() -> None:
    """銘柄ごとの最終保存日に応じて異なる範囲を作る。"""

    repository = FakeLatestMarketBarReader(
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
            "9984": None,
        }
    )
    calendar = FakeTradingCalendarReader(
        create_business_dates(
            1,
            5,
        )
    )

    plan = IncrementalUpdatePlanner(
        repository=repository,
        calendar_reader=calendar,
    ).create_plan(
        codes=[
            "7203",
            "8306",
            "9984",
        ],
        initial_start_date=date(2026, 7, 1),
        target_end_date=date(2026, 7, 5),
        interval_minutes=5,
        today=date(2026, 7, 10),
    )

    tasks_by_code = {
        task.code: task
        for task in plan.tasks
    }

    assert tasks_by_code[
        "7203"
    ].business_dates == (
        date(2026, 7, 3),
        date(2026, 7, 4),
        date(2026, 7, 5),
    )

    assert tasks_by_code[
        "8306"
    ].business_dates == (
        date(2026, 7, 5),
    )

    assert tasks_by_code[
        "9984"
    ].business_dates == (
        date(2026, 7, 1),
        date(2026, 7, 2),
        date(2026, 7, 3),
        date(2026, 7, 4),
        date(2026, 7, 5),
    )

    assert plan.code_count == 3
    assert plan.update_code_count == 3
    assert plan.total_business_date_count == 9

    assert calendar.calls == [
        (
            date(2026, 7, 1),
            date(2026, 7, 5),
        )
    ]


def test_planner_filters_sorts_and_deduplicates_calendar_dates() -> None:
    """営業日を期間内へ限定し、昇順・重複なしにする。"""

    repository = FakeLatestMarketBarReader(
        {
            "7203": None,
        }
    )
    calendar = FakeTradingCalendarReader(
        [
            date(2026, 7, 4),
            date(2026, 7, 2),
            date(2026, 7, 2),
            date(2026, 6, 30),
            date(2026, 7, 6),
            date(2026, 7, 3),
        ]
    )

    plan = IncrementalUpdatePlanner(
        repository=repository,
        calendar_reader=calendar,
    ).create_plan(
        codes=["7203"],
        initial_start_date=date(2026, 7, 1),
        target_end_date=date(2026, 7, 5),
        today=date(2026, 7, 10),
    )

    assert plan.tasks[0].business_dates == (
        date(2026, 7, 2),
        date(2026, 7, 3),
        date(2026, 7, 4),
    )


def test_planner_removes_duplicate_codes() -> None:
    """重複銘柄を1件にまとめる。"""

    repository = FakeLatestMarketBarReader(
        {
            "7203": None,
        }
    )
    calendar = FakeTradingCalendarReader(
        [
            date(2026, 7, 1),
        ]
    )

    plan = IncrementalUpdatePlanner(
        repository=repository,
        calendar_reader=calendar,
    ).create_plan(
        codes=[
            "7203",
            "7203",
        ],
        initial_start_date=date(2026, 7, 1),
        target_end_date=date(2026, 7, 1),
        today=date(2026, 7, 10),
    )

    assert plan.code_count == 1
    assert len(repository.calls) == 1
    assert plan.tasks[0].code == "7203"


@pytest.mark.parametrize(
    (
        "codes",
        "initial_start_date",
        "target_end_date",
        "interval_minutes",
        "today",
        "message",
    ),
    [
        (
            [],
            date(2026, 7, 1),
            date(2026, 7, 5),
            5,
            date(2026, 7, 10),
            "銘柄コード",
        ),
        (
            ["ABCD"],
            date(2026, 7, 1),
            date(2026, 7, 5),
            5,
            date(2026, 7, 10),
            "数字",
        ),
        (
            ["7203"],
            date(2026, 7, 5),
            date(2026, 7, 1),
            5,
            date(2026, 7, 10),
            "初回取得開始日",
        ),
        (
            ["7203"],
            date(2026, 7, 1),
            date(2026, 7, 5),
            0,
            date(2026, 7, 10),
            "時間足",
        ),
        (
            ["7203"],
            date(2026, 7, 1),
            date(2026, 7, 11),
            5,
            date(2026, 7, 10),
            "未来日",
        ),
    ],
)
def test_planner_rejects_invalid_arguments(
    codes: list[str],
    initial_start_date: date,
    target_end_date: date,
    interval_minutes: int,
    today: date,
    message: str,
) -> None:
    """不正な差分更新条件を拒否する。"""

    planner = IncrementalUpdatePlanner(
        repository=FakeLatestMarketBarReader({}),
        calendar_reader=FakeTradingCalendarReader([]),
    )

    with pytest.raises(
        ValueError,
        match=message,
    ):
        planner.create_plan(
            codes=codes,
            initial_start_date=initial_start_date,
            target_end_date=target_end_date,
            interval_minutes=interval_minutes,
            today=today,
        )