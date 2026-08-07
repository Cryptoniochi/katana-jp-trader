"""Universe Daily Schedulerの状態モデル。"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, time
from enum import StrEnum
from typing import Any


class UniverseDailyScheduleState(StrEnum):
    DISABLED = "disabled"
    CLOSED_DAY = "closed_day"
    WAITING = "waiting"
    RUNNING = "running"
    RETRY_WAIT = "retry_wait"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class UniverseDailyScheduleSettings:
    run_at: time = time(15, 36)
    retry_interval_seconds: float = 300.0
    command_timeout_seconds: float = 900.0
    minimum_success_ratio: float = 0.80

    def __post_init__(self) -> None:
        if self.retry_interval_seconds <= 0:
            raise ValueError(
                "再試行間隔は0より大きい必要があります。"
            )
        if self.command_timeout_seconds <= 0:
            raise ValueError(
                "コマンドタイムアウトは0より大きい必要があります。"
            )
        if not 0 < self.minimum_success_ratio <= 1:
            raise ValueError(
                "最低成功率は0より大きく1以下です。"
            )


@dataclass(frozen=True, slots=True)
class UniverseDailyScheduleStatus:
    generated_at: datetime
    target_date: str
    state: UniverseDailyScheduleState
    business_day: bool
    enabled: bool
    next_action_at: datetime | None
    last_attempt_at: datetime | None
    last_exit_code: int | None
    requested_count: int | None
    collected_count: int | None
    success_ratio: float | None
    message: str
    settings: UniverseDailyScheduleSettings

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["generated_at"] = (
            self.generated_at.isoformat()
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
        payload["settings"]["run_at"] = (
            self.settings.run_at.isoformat(
                timespec="minutes"
            )
        )
        return payload
