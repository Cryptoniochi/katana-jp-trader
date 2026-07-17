"""長時間運転セッションの共通モデル。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum


class RuntimeSessionStatus(StrEnum):
    RUNNING = "running"
    STOPPED = "stopped"
    FAILED = "failed"


class RuntimeSessionStopReason(StrEnum):
    NORMAL = "normal"
    MANUAL = "manual"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class RuntimeDailySummary:
    session_id: str
    operating_date: date
    started_at: datetime
    ended_at: datetime
    cycle_count: int
    successful_cycle_count: int
    failed_cycle_count: int
    heartbeat_count: int
    restart_count: int
    error_count: int

    def __post_init__(self) -> None:
        session_id = self.session_id.strip()
        if not session_id:
            raise ValueError("Runtime Session IDを指定してください。")
        if self.started_at.tzinfo is None or self.ended_at.tzinfo is None:
            raise ValueError("開始・終了日時にはタイムゾーンが必要です。")
        if self.ended_at < self.started_at:
            raise ValueError("終了日時は開始日時以後である必要があります。")
        values = (
            self.cycle_count,
            self.successful_cycle_count,
            self.failed_cycle_count,
            self.heartbeat_count,
            self.restart_count,
            self.error_count,
        )
        if any(value < 0 for value in values):
            raise ValueError("日次集計値は0以上である必要があります。")
        if self.successful_cycle_count + self.failed_cycle_count != self.cycle_count:
            raise ValueError("成功・失敗サイクル数がサイクル数と一致しません。")
        object.__setattr__(self, "session_id", session_id)

    @property
    def duration_seconds(self) -> float:
        return (self.ended_at - self.started_at).total_seconds()

    @property
    def success_rate(self) -> float:
        if self.cycle_count == 0:
            return 0.0
        return self.successful_cycle_count / self.cycle_count


@dataclass(frozen=True, slots=True)
class RuntimeSessionSnapshot:
    session_id: str
    status: RuntimeSessionStatus
    started_at: datetime
    checked_at: datetime
    active_date: date
    cycle_count: int
    successful_cycle_count: int
    failed_cycle_count: int
    heartbeat_count: int
    restart_count: int
    error_count: int
    completed_day_count: int
    ended_at: datetime | None = None
    stop_reason: RuntimeSessionStopReason | None = None
    message: str | None = None

    def __post_init__(self) -> None:
        session_id = self.session_id.strip()
        if not session_id:
            raise ValueError("Runtime Session IDを指定してください。")
        if self.started_at.tzinfo is None or self.checked_at.tzinfo is None:
            raise ValueError("開始・確認日時にはタイムゾーンが必要です。")
        if self.checked_at < self.started_at:
            raise ValueError("確認日時は開始日時以後である必要があります。")
        if self.status is RuntimeSessionStatus.RUNNING:
            if self.ended_at is not None or self.stop_reason is not None:
                raise ValueError("稼働中セッションに終了情報は設定できません。")
        else:
            if self.ended_at is None or self.stop_reason is None:
                raise ValueError("終了済みセッションには終了情報が必要です。")
            if self.ended_at.tzinfo is None:
                raise ValueError("終了日時にはタイムゾーンが必要です。")
        values = (
            self.cycle_count,
            self.successful_cycle_count,
            self.failed_cycle_count,
            self.heartbeat_count,
            self.restart_count,
            self.error_count,
            self.completed_day_count,
        )
        if any(value < 0 for value in values):
            raise ValueError("セッション集計値は0以上である必要があります。")
        if self.successful_cycle_count + self.failed_cycle_count != self.cycle_count:
            raise ValueError("成功・失敗サイクル数がサイクル数と一致しません。")
        object.__setattr__(self, "session_id", session_id)
        object.__setattr__(
            self,
            "message",
            None if self.message is None else self.message.strip() or None,
        )

    @property
    def uptime_seconds(self) -> float:
        endpoint = self.ended_at or self.checked_at
        return (endpoint - self.started_at).total_seconds()

    @property
    def is_running(self) -> bool:
        return self.status is RuntimeSessionStatus.RUNNING


@dataclass(frozen=True, slots=True)
class RuntimeRotationResult:
    rotated: bool
    previous_summary: RuntimeDailySummary | None
    snapshot: RuntimeSessionSnapshot

    def __post_init__(self) -> None:
        if self.rotated != (self.previous_summary is not None):
            raise ValueError("ローテーション結果の整合性がありません。")


@dataclass(frozen=True, slots=True)
class RuntimeSessionReport:
    snapshot: RuntimeSessionSnapshot
    daily_summaries: tuple[RuntimeDailySummary, ...]

    def __post_init__(self) -> None:
        if self.snapshot.is_running:
            raise ValueError("稼働中セッションから最終レポートは作成できません。")

    @property
    def total_cycle_count(self) -> int:
        return sum(item.cycle_count for item in self.daily_summaries)

    @property
    def total_error_count(self) -> int:
        return sum(item.error_count for item in self.daily_summaries)
