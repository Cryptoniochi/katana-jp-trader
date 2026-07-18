"""TokyoMarketCalendarのテスト。"""

from datetime import date

import pytest

from app.market.market_calendar import (
    TokyoMarketCalendar,
)


def test_weekday_is_business_day() -> None:
    calendar = TokyoMarketCalendar()

    assert calendar.is_business_day(
        date(2026, 7, 21)
    )


def test_weekend_and_official_holiday_are_closed() -> None:
    calendar = TokyoMarketCalendar()

    assert not calendar.is_business_day(
        date(2026, 7, 18)
    )
    assert not calendar.is_business_day(
        date(2026, 7, 20)
    )


def test_year_end_and_new_year_are_closed() -> None:
    calendar = TokyoMarketCalendar.with_custom_holidays(())

    assert not calendar.is_business_day(
        date(2026, 12, 31)
    )
    assert not calendar.is_business_day(
        date(2027, 1, 2)
    )


def test_additional_open_and_closed_dates_override_defaults() -> None:
    calendar = TokyoMarketCalendar(
        additional_closed_dates=frozenset(
            {date(2026, 7, 21)}
        ),
        additional_open_dates=frozenset(
            {date(2026, 7, 18)}
        ),
    )

    assert not calendar.is_business_day(
        date(2026, 7, 21)
    )
    assert calendar.is_business_day(
        date(2026, 7, 18)
    )


def test_overlapping_overrides_are_rejected() -> None:
    target = date(2026, 7, 21)

    with pytest.raises(ValueError, match="重複"):
        TokyoMarketCalendar(
            additional_closed_dates=frozenset(
                {target}
            ),
            additional_open_dates=frozenset(
                {target}
            ),
        )


def test_next_business_day_skips_holiday_and_weekend() -> None:
    calendar = TokyoMarketCalendar()

    assert calendar.next_business_day(
        date(2026, 7, 17)
    ) == date(2026, 7, 21)
