"""Morning Pre-Flight自動実行スケジュールのモデル。"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, time
from enum import StrEnum
from typing import Any


class MorningPreflightScheduleState(StrEnum):
    """Morning Pre-Flightスケジューラ状態。"""

    DISABLED = "disabled"
    CLOSED_DAY = "closed_day"
    WAITING = "waiting"
    RUNNING = "running"
    COMPLETED = "completed"
    RETRY_WAIT = "retry_wait"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class MorningPreflightScheduleSettings:
    """Morning Pre-Flight自動実行設定。"""

    run_at: time = time(8, 40)
    retry_interval_seconds: float = 300.0
    command_timeout_seconds: float = 180.0

    def __post_init__(self) -> None:
        if self.retry_interval_seconds <= 0:
            raise ValueError(
                "再試行間隔は0より大きい必要があります。"
            )

        if self.command_timeout_seconds <= 0:
            raise ValueError(
                "コマンドタイムアウトは0より大きい必要があります。"
            )


@dataclass(frozen=True, slots=True)
class MorningPreflightScheduleStatus:
    """Morning Pre-Flightスケジューラ状態。"""

    generated_at: datetime
    target_date: date
    state: MorningPreflightScheduleState
    business_day: bool
    enabled: bool
    next_action_at: datetime | None
    last_attempt_at: datetime | None
    last_exit_code: int | None
    message: str
    settings: MorningPreflightScheduleSettings

    def __post_init__(self) -> None:
        for value in (
            self.generated_at,
            self.next_action_at,
            self.last_attempt_at,
        ):
            if value is not None and value.tzinfo is None:
                raise ValueError(
                    "日時にはタイムゾーンが必要です。"
                )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["generated_at"] = (
            self.generated_at.isoformat()
        )
        payload["target_date"] = (
            self.target_date.isoformat()
        )
        payload["state"] = self.state.value
        payload["next_action_at"] = (
            self.next_action_at.isoformat()
            if self.next_action_at is not None
            else None
        )
        payload["last_attempt_at"] = (
            self.last_attempt_at.isoformat()
            if self.last_attempt_at is not None
            else None
        )
        payload["settings"] = {
            "run_at": self.settings.run_at.isoformat(
                timespec="minutes"
            ),
            "retry_interval_seconds": (
                self.settings.retry_interval_seconds
            ),
            "command_timeout_seconds": (
                self.settings.command_timeout_seconds
            ),
        }
        return payload
