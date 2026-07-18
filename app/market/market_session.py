"""東京証券取引所の現物株セッションモデル。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from enum import StrEnum


class TokyoMarketSession(StrEnum):
    """東証現物株の現在セッション。"""

    CLOSED = "closed"
    PRE_OPEN = "pre_open"
    MORNING = "morning"
    LUNCH = "lunch"
    AFTERNOON = "afternoon"
    AFTER_CLOSE = "after_close"


@dataclass(frozen=True, slots=True)
class TokyoMarketSessionSchedule:
    """東証現物株の時刻設定。"""

    pre_open_start: time = time(8, 0)
    morning_open: time = time(9, 0)
    morning_close: time = time(11, 30)
    afternoon_order_acceptance: time = time(12, 5)
    afternoon_open: time = time(12, 30)
    afternoon_close: time = time(15, 30)

    def __post_init__(self) -> None:
        """セッション時刻の順序を検証する。"""

        values = (
            self.pre_open_start,
            self.morning_open,
            self.morning_close,
            self.afternoon_order_acceptance,
            self.afternoon_open,
            self.afternoon_close,
        )

        if list(values) != sorted(values):
            raise ValueError(
                "市場セッション時刻は昇順で指定してください。"
            )

    def resolve(self, local_time: time) -> TokyoMarketSession:
        """営業日のローカル時刻からセッションを返す。"""

        if local_time < self.pre_open_start:
            return TokyoMarketSession.CLOSED

        if local_time < self.morning_open:
            return TokyoMarketSession.PRE_OPEN

        if local_time <= self.morning_close:
            return TokyoMarketSession.MORNING

        if local_time < self.afternoon_open:
            return TokyoMarketSession.LUNCH

        if local_time <= self.afternoon_close:
            return TokyoMarketSession.AFTERNOON

        return TokyoMarketSession.AFTER_CLOSE

    @staticmethod
    def is_trading_session(
        session: TokyoMarketSession,
    ) -> bool:
        """売買サイクル実行対象セッションか返す。"""

        return session in {
            TokyoMarketSession.MORNING,
            TokyoMarketSession.AFTERNOON,
        }
