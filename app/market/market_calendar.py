"""東京証券取引所の営業日判定。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Iterable


OFFICIAL_MARKET_HOLIDAYS_2026 = frozenset(
    {
        date(2026, 1, 1),
        date(2026, 1, 2),
        date(2026, 1, 3),
        date(2026, 1, 12),
        date(2026, 2, 11),
        date(2026, 2, 23),
        date(2026, 3, 20),
        date(2026, 4, 29),
        date(2026, 5, 3),
        date(2026, 5, 4),
        date(2026, 5, 5),
        date(2026, 5, 6),
        date(2026, 7, 20),
        date(2026, 8, 11),
        date(2026, 9, 21),
        date(2026, 9, 22),
        date(2026, 9, 23),
        date(2026, 10, 12),
        date(2026, 11, 3),
        date(2026, 11, 23),
        date(2026, 12, 31),
    }
)

OFFICIAL_MARKET_HOLIDAYS_2027 = frozenset(
    {
        date(2027, 1, 1),
        date(2027, 1, 2),
        date(2027, 1, 3),
        date(2027, 1, 11),
        date(2027, 2, 11),
        date(2027, 2, 23),
        date(2027, 3, 21),
        date(2027, 3, 22),
        date(2027, 4, 29),
        date(2027, 5, 3),
        date(2027, 5, 4),
        date(2027, 5, 5),
        date(2027, 7, 19),
        date(2027, 8, 11),
        date(2027, 9, 20),
        date(2027, 9, 23),
        date(2027, 10, 11),
        date(2027, 11, 3),
        date(2027, 11, 23),
        date(2027, 12, 31),
    }
)

DEFAULT_MARKET_HOLIDAYS = (
    OFFICIAL_MARKET_HOLIDAYS_2026
    | OFFICIAL_MARKET_HOLIDAYS_2027
)


@dataclass(frozen=True, slots=True)
class TokyoMarketCalendar:
    """土日・JPX休場日・追加休場日を判定する。"""

    holidays: frozenset[date] = field(
        default_factory=lambda: DEFAULT_MARKET_HOLIDAYS
    )
    additional_closed_dates: frozenset[date] = field(
        default_factory=frozenset
    )
    additional_open_dates: frozenset[date] = field(
        default_factory=frozenset
    )

    def __post_init__(self) -> None:
        """日付集合を防御的に正規化する。"""

        object.__setattr__(
            self,
            "holidays",
            frozenset(self.holidays),
        )
        object.__setattr__(
            self,
            "additional_closed_dates",
            frozenset(self.additional_closed_dates),
        )
        object.__setattr__(
            self,
            "additional_open_dates",
            frozenset(self.additional_open_dates),
        )

        overlap = (
            self.additional_closed_dates
            & self.additional_open_dates
        )
        if overlap:
            raise ValueError(
                "追加営業日と追加休場日が重複しています。 "
                f"dates={sorted(overlap)}"
            )

    @classmethod
    def with_custom_holidays(
        cls,
        holidays: Iterable[date],
        *,
        additional_closed_dates: Iterable[date] = (),
        additional_open_dates: Iterable[date] = (),
    ) -> "TokyoMarketCalendar":
        """任意の祝日一覧でCalendarを作成する。"""

        return cls(
            holidays=frozenset(holidays),
            additional_closed_dates=frozenset(
                additional_closed_dates
            ),
            additional_open_dates=frozenset(
                additional_open_dates
            ),
        )

    def is_business_day(self, target_date: date) -> bool:
        """対象日が東証営業日か返す。"""

        if target_date in self.additional_open_dates:
            return True

        if target_date in self.additional_closed_dates:
            return False

        if target_date.weekday() >= 5:
            return False

        if target_date in self.holidays:
            return False

        if (
            target_date.month == 1
            and target_date.day in {1, 2, 3}
        ):
            return False

        if (
            target_date.month == 12
            and target_date.day == 31
        ):
            return False

        return True

    def next_business_day(
        self,
        target_date: date,
        *,
        include_current: bool = False,
    ) -> date:
        """対象日以後の次営業日を返す。"""

        candidate = (
            target_date
            if include_current
            else target_date + timedelta(days=1)
        )

        for _ in range(370):
            if self.is_business_day(candidate):
                return candidate
            candidate += timedelta(days=1)

        raise RuntimeError(
            "370日以内に次の営業日を取得できませんでした。"
        )
