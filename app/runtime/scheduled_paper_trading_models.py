"""営業日Paper Tradingスケジュールのモデル。"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, time
from enum import StrEnum
from typing import Any


class ScheduledTradingState(StrEnum):
    """スケジュール制御の現在状態。"""

    DISABLED = "disabled"
    CLOSED_DAY = "closed_day"
    BEFORE_START = "before_start"
    STARTING = "starting"
    RUNNING = "running"
    LUNCH_BREAK = "lunch_break"
    STOPPING = "stopping"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class TradingScheduleSettings:
    """東京市場向けPaper Trading運用時間。"""

    start_at: time = time(8, 45)
    morning_open_at: time = time(9, 0)
    lunch_start_at: time = time(11, 30)
    lunch_end_at: time = time(12, 30)
    market_close_at: time = time(15, 30)
    stop_at: time = time(15, 35)

    def __post_init__(self) -> None:
        ordered = (
            self.start_at,
            self.morning_open_at,
            self.lunch_start_at,
            self.lunch_end_at,
            self.market_close_at,
            self.stop_at,
        )

        if tuple(sorted(ordered)) != ordered:
            raise ValueError(
                "運用時刻は昇順で指定してください。"
            )


@dataclass(frozen=True, slots=True)
class ScheduledTradingStatus:
    """Dashboardへ保存するスケジュール状態。"""

    generated_at: datetime
    trading_date: date
    state: ScheduledTradingState
    business_day: bool
    enabled: bool
    process_id: int | None
    last_exit_code: int | None
    next_action_at: datetime | None
    message: str
    settings: TradingScheduleSettings

    def __post_init__(self) -> None:
        if self.generated_at.tzinfo is None:
            raise ValueError(
                "生成日時にはタイムゾーンが必要です。"
            )

        if (
            self.next_action_at is not None
            and self.next_action_at.tzinfo is None
        ):
            raise ValueError(
                "次回実行日時にはタイムゾーンが必要です。"
            )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["generated_at"] = (
            self.generated_at.isoformat()
        )
        payload["trading_date"] = (
            self.trading_date.isoformat()
        )
        payload["state"] = self.state.value
        payload["next_action_at"] = (
            self.next_action_at.isoformat()
            if self.next_action_at is not None
            else None
        )
        payload["settings"] = {
            key: value.isoformat(
                timespec="minutes"
            )
            for key, value in payload[
                "settings"
            ].items()
        }
        return payload
