"""Dynamic Watchlist自動更新スケジュールのモデル。"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, time
from enum import StrEnum
from typing import Any


class DynamicWatchlistScheduleState(StrEnum):
    """Dynamic Watchlistスケジューラ状態。"""

    DISABLED = "disabled"
    CLOSED_DAY = "closed_day"
    WAITING = "waiting"
    RUNNING = "running"
    COMPLETED = "completed"
    RETRY_WAIT = "retry_wait"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class DynamicWatchlistScheduleSettings:
    """Dynamic Watchlist自動更新設定。"""

    run_at: time = time(8, 20)
    retry_interval_seconds: float = 300.0
    command_timeout_seconds: float = 180.0
    minimum_symbols: int = 5
    maximum_symbols: int = 50
    capital_limit: float = 1_000_000.0
    purchase_budget: float = 950_000.0

    def __post_init__(self) -> None:
        if self.retry_interval_seconds <= 0:
            raise ValueError(
                "再試行間隔は0より大きい必要があります。"
            )
        if self.command_timeout_seconds <= 0:
            raise ValueError(
                "コマンドタイムアウトは0より大きい必要があります。"
            )
        if not 1 <= self.minimum_symbols <= self.maximum_symbols:
            raise ValueError(
                "最低銘柄数は1以上かつ最大銘柄数以下です。"
            )
        if self.capital_limit <= 0:
            raise ValueError(
                "運用資金上限は0より大きい必要があります。"
            )
        if not 0 < self.purchase_budget <= self.capital_limit:
            raise ValueError(
                "購入予算は運用資金上限以下である必要があります。"
            )


@dataclass(frozen=True, slots=True)
class DynamicWatchlistScheduleStatus:
    """Dynamic Watchlistスケジューラ状態。"""

    generated_at: datetime
    target_date: date
    state: DynamicWatchlistScheduleState
    business_day: bool
    enabled: bool
    next_action_at: datetime | None
    last_attempt_at: datetime | None
    last_exit_code: int | None
    selected_count: int | None
    applied: bool | None
    message: str
    settings: DynamicWatchlistScheduleSettings

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
        return {
            "generated_at": self.generated_at.isoformat(),
            "target_date": self.target_date.isoformat(),
            "state": self.state.value,
            "business_day": self.business_day,
            "enabled": self.enabled,
            "next_action_at": (
                self.next_action_at.isoformat()
                if self.next_action_at is not None
                else None
            ),
            "last_attempt_at": (
                self.last_attempt_at.isoformat()
                if self.last_attempt_at is not None
                else None
            ),
            "last_exit_code": self.last_exit_code,
            "selected_count": self.selected_count,
            "applied": self.applied,
            "message": self.message,
            "settings": {
                **asdict(self.settings),
                "run_at": self.settings.run_at.isoformat(
                    timespec="minutes"
                ),
            },
        }
