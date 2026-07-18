"""東京市場の現在状態と次回起動時刻を計算する。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from zoneinfo import ZoneInfo

from app.market.market_calendar import TokyoMarketCalendar
from app.market.market_session import (
    TokyoMarketSession,
    TokyoMarketSessionSchedule,
)


TOKYO_TIME_ZONE = ZoneInfo("Asia/Tokyo")


@dataclass(frozen=True, slots=True)
class TokyoMarketClockSnapshot:
    """東京市場の現在状態。"""

    observed_at: datetime
    local_at: datetime
    business_day: bool
    session: TokyoMarketSession
    next_trading_at: datetime
    wait_seconds: float

    def __post_init__(self) -> None:
        """日時と待機秒数を検証する。"""

        if (
            self.observed_at.tzinfo is None
            or self.local_at.tzinfo is None
            or self.next_trading_at.tzinfo is None
        ):
            raise ValueError(
                "Market Clock日時にはタイムゾーンが必要です。"
            )

        if self.wait_seconds < 0:
            raise ValueError(
                "待機秒数は0以上である必要があります。"
            )

    @property
    def is_open(self) -> bool:
        """現在が売買セッション中か返す。"""

        return TokyoMarketSessionSchedule.is_trading_session(
            self.session
        )


class TokyoMarketClock:
    """CalendarとSession Scheduleを統合する。"""

    def __init__(
        self,
        *,
        calendar: TokyoMarketCalendar | None = None,
        schedule: TokyoMarketSessionSchedule | None = None,
    ) -> None:
        """CalendarとSession Scheduleを設定する。"""

        self.calendar = calendar or TokyoMarketCalendar()
        self.schedule = (
            schedule or TokyoMarketSessionSchedule()
        )

    def snapshot(
        self,
        observed_at: datetime,
    ) -> TokyoMarketClockSnapshot:
        """現在状態・次回取引開始・待機秒数を返す。"""

        if observed_at.tzinfo is None:
            raise ValueError(
                "観測日時にはタイムゾーンが必要です。"
            )

        local_at = observed_at.astimezone(
            TOKYO_TIME_ZONE
        )
        business_day = self.calendar.is_business_day(
            local_at.date()
        )

        if not business_day:
            session = TokyoMarketSession.CLOSED
            next_trading_at = self._next_business_open(
                local_at
            )
        else:
            session = self.schedule.resolve(
                local_at.timetz().replace(tzinfo=None)
            )
            next_trading_at = self._next_trading_time(
                local_at,
                session,
            )

        wait_seconds = max(
            0.0,
            (
                next_trading_at - local_at
            ).total_seconds(),
        )

        return TokyoMarketClockSnapshot(
            observed_at=observed_at,
            local_at=local_at,
            business_day=business_day,
            session=session,
            next_trading_at=next_trading_at,
            wait_seconds=wait_seconds,
        )

    def _next_trading_time(
        self,
        local_at: datetime,
        session: TokyoMarketSession,
    ) -> datetime:
        """営業日の次回取引可能時刻を返す。"""

        if TokyoMarketSessionSchedule.is_trading_session(
            session
        ):
            return local_at

        if session in {
            TokyoMarketSession.CLOSED,
            TokyoMarketSession.PRE_OPEN,
        }:
            return self._combine(
                local_at.date(),
                self.schedule.morning_open,
            )

        if session is TokyoMarketSession.LUNCH:
            return self._combine(
                local_at.date(),
                self.schedule.afternoon_open,
            )

        return self._next_business_open(local_at)

    def _next_business_open(
        self,
        local_at: datetime,
    ) -> datetime:
        """次営業日の前場開始時刻を返す。"""

        next_date = self.calendar.next_business_day(
            local_at.date()
        )
        return self._combine(
            next_date,
            self.schedule.morning_open,
        )

    @staticmethod
    def _combine(
        target_date,
        target_time: time,
    ) -> datetime:
        """東京時刻の日時を作成する。"""

        return datetime.combine(
            target_date,
            target_time,
            tzinfo=TOKYO_TIME_ZONE,
        )
