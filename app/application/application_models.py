"""Application Lifecycleの共通モデル。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class ApplicationState(StrEnum):
    """Applicationのライフサイクル状態。"""

    CREATED = "created"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"


class ApplicationStopReason(StrEnum):
    """Application停止理由。"""

    NORMAL = "normal"
    MANUAL = "manual"
    ERROR = "error"
    SIGNAL = "signal"


@dataclass(frozen=True, slots=True)
class ApplicationSnapshot:
    """Applicationの現在状態。"""

    application_name: str
    state: ApplicationState
    created_at: datetime
    checked_at: datetime
    started_at: datetime | None = None
    stopping_at: datetime | None = None
    stopped_at: datetime | None = None
    stop_reason: ApplicationStopReason | None = None
    message: str | None = None

    def __post_init__(self) -> None:
        """状態・日時・メッセージの整合性を検証する。"""

        application_name = self.application_name.strip()
        message = (
            None
            if self.message is None
            else self.message.strip() or None
        )

        if not application_name:
            raise ValueError(
                "Application名を指定してください。"
            )

        for name, value in {
            "作成日時": self.created_at,
            "確認日時": self.checked_at,
        }.items():
            if value.tzinfo is None:
                raise ValueError(
                    f"{name}にはタイムゾーンが必要です。"
                )

        if self.checked_at < self.created_at:
            raise ValueError(
                "確認日時は作成日時以後である必要があります。"
            )

        for name, value in {
            "開始日時": self.started_at,
            "停止開始日時": self.stopping_at,
            "停止完了日時": self.stopped_at,
        }.items():
            if value is not None and value.tzinfo is None:
                raise ValueError(
                    f"{name}にはタイムゾーンが必要です。"
                )

        if self.started_at is not None:
            if self.started_at < self.created_at:
                raise ValueError(
                    "開始日時は作成日時以後である必要があります。"
                )

        if self.stopping_at is not None:
            if self.started_at is None:
                raise ValueError(
                    "停止開始日時には開始日時が必要です。"
                )
            if self.stopping_at < self.started_at:
                raise ValueError(
                    "停止開始日時は開始日時以後である必要があります。"
                )

        if self.stopped_at is not None:
            if self.started_at is None:
                raise ValueError(
                    "停止完了日時には開始日時が必要です。"
                )
            if self.stopped_at < self.started_at:
                raise ValueError(
                    "停止完了日時は開始日時以後である必要があります。"
                )
            if (
                self.stopping_at is not None
                and self.stopped_at < self.stopping_at
            ):
                raise ValueError(
                    "停止完了日時は停止開始日時以後である必要があります。"
                )

        if self.state is ApplicationState.CREATED:
            if any(
                value is not None
                for value in (
                    self.started_at,
                    self.stopping_at,
                    self.stopped_at,
                    self.stop_reason,
                )
            ):
                raise ValueError(
                    "CREATED状態には開始・停止情報を設定できません。"
                )

        if self.state in {
            ApplicationState.STARTING,
            ApplicationState.RUNNING,
        }:
            if self.started_at is None:
                raise ValueError(
                    "開始済み状態には開始日時が必要です。"
                )
            if any(
                value is not None
                for value in (
                    self.stopping_at,
                    self.stopped_at,
                    self.stop_reason,
                )
            ):
                raise ValueError(
                    "稼働中状態には停止情報を設定できません。"
                )

        if self.state is ApplicationState.STOPPING:
            if (
                self.started_at is None
                or self.stopping_at is None
            ):
                raise ValueError(
                    "STOPPING状態には開始・停止開始日時が必要です。"
                )
            if self.stopped_at is not None:
                raise ValueError(
                    "STOPPING状態には停止完了日時を設定できません。"
                )
            if self.stop_reason is None:
                raise ValueError(
                    "STOPPING状態には停止理由が必要です。"
                )

        if self.state in {
            ApplicationState.STOPPED,
            ApplicationState.FAILED,
        }:
            if (
                self.started_at is None
                or self.stopping_at is None
                or self.stopped_at is None
                or self.stop_reason is None
            ):
                raise ValueError(
                    "終了状態には開始・停止日時・停止理由が必要です。"
                )

        object.__setattr__(
            self,
            "application_name",
            application_name,
        )
        object.__setattr__(
            self,
            "message",
            message,
        )

    @property
    def uptime_seconds(self) -> float:
        """開始から確認または停止完了までの経過秒数を返す。"""

        if self.started_at is None:
            return 0.0

        endpoint = self.stopped_at or self.checked_at
        return (
            endpoint - self.started_at
        ).total_seconds()

    @property
    def is_running(self) -> bool:
        """Applicationが稼働中か返す。"""

        return self.state is ApplicationState.RUNNING

    @property
    def is_terminal(self) -> bool:
        """Applicationが終了状態か返す。"""

        return self.state in {
            ApplicationState.STOPPED,
            ApplicationState.FAILED,
        }


@dataclass(frozen=True, slots=True)
class ApplicationReport:
    """終了したApplicationの最終レポート。"""

    snapshot: ApplicationSnapshot
    graceful_shutdown: bool

    def __post_init__(self) -> None:
        """最終レポートを検証する。"""

        if not self.snapshot.is_terminal:
            raise ValueError(
                "終了状態のSnapshotが必要です。"
            )

        if (
            self.graceful_shutdown
            and self.snapshot.state is ApplicationState.FAILED
        ):
            raise ValueError(
                "FAILED状態をGraceful Shutdownとして扱えません。"
            )
