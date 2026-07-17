"""Long Running Supervisorの共通モデル。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class SupervisorStatus(StrEnum):
    """Supervisorが管理するWorker状態。"""

    STARTING = "starting"
    RUNNING = "running"
    STALE = "stale"
    RESTARTING = "restarting"
    STOPPED = "stopped"
    FAILED = "failed"


class SupervisorStopReason(StrEnum):
    """Worker停止理由。"""

    NORMAL = "normal"
    ERROR = "error"
    HEARTBEAT_TIMEOUT = "heartbeat_timeout"
    RESTART_LIMIT = "restart_limit"
    MANUAL = "manual"


@dataclass(frozen=True, slots=True)
class SupervisorPolicy:
    """Heartbeatと再起動に関するSupervisor方針。"""

    heartbeat_timeout_seconds: float = 120.0
    restart_cooldown_seconds: float = 30.0
    maximum_restart_count: int = 3

    def __post_init__(self) -> None:
        """Supervisor方針を検証する。"""

        if self.heartbeat_timeout_seconds <= 0:
            raise ValueError(
                "Heartbeatタイムアウトは0より大きい必要があります。"
            )

        if self.restart_cooldown_seconds < 0:
            raise ValueError(
                "再起動Cooldownは0以上である必要があります。"
            )

        if self.maximum_restart_count < 0:
            raise ValueError(
                "最大再起動回数は0以上である必要があります。"
            )


@dataclass(frozen=True, slots=True)
class SupervisorSnapshot:
    """ある時点のSupervisor状態。"""

    worker_name: str
    status: SupervisorStatus
    started_at: datetime
    checked_at: datetime
    last_heartbeat_at: datetime | None
    last_restart_at: datetime | None
    restart_count: int
    stop_reason: SupervisorStopReason | None
    message: str | None = None

    def __post_init__(self) -> None:
        """Supervisor状態を検証して正規化する。"""

        worker_name = self.worker_name.strip()
        message = (
            None
            if self.message is None
            else self.message.strip()
        )

        if not worker_name:
            raise ValueError(
                "Worker名を指定してください。"
            )

        for name, value in {
            "開始日時": self.started_at,
            "確認日時": self.checked_at,
        }.items():
            if value.tzinfo is None:
                raise ValueError(
                    f"{name}にはタイムゾーンが必要です。"
                )

        if self.checked_at < self.started_at:
            raise ValueError(
                "確認日時は開始日時以後である必要があります。"
            )

        if (
            self.last_heartbeat_at is not None
            and self.last_heartbeat_at.tzinfo is None
        ):
            raise ValueError(
                "最終Heartbeat日時にはタイムゾーンが必要です。"
            )

        if (
            self.last_restart_at is not None
            and self.last_restart_at.tzinfo is None
        ):
            raise ValueError(
                "最終再起動日時にはタイムゾーンが必要です。"
            )

        if self.restart_count < 0:
            raise ValueError(
                "再起動回数は0以上である必要があります。"
            )

        if (
            self.status
            in {
                SupervisorStatus.STOPPED,
                SupervisorStatus.FAILED,
            }
            and self.stop_reason is None
        ):
            raise ValueError(
                "停止・失敗状態には停止理由が必要です。"
            )

        object.__setattr__(
            self,
            "worker_name",
            worker_name,
        )
        object.__setattr__(
            self,
            "message",
            message or None,
        )

    @property
    def uptime_seconds(self) -> float:
        """開始から確認時点までの稼働秒数を返す。"""

        return (
            self.checked_at - self.started_at
        ).total_seconds()

    @property
    def heartbeat_age_seconds(self) -> float | None:
        """最終Heartbeatからの経過秒数を返す。"""

        if self.last_heartbeat_at is None:
            return None

        return (
            self.checked_at - self.last_heartbeat_at
        ).total_seconds()

    @property
    def is_running(self) -> bool:
        """Workerが稼働中か返す。"""

        return self.status is SupervisorStatus.RUNNING

    @property
    def requires_attention(self) -> bool:
        """運用者の確認が必要か返す。"""

        return self.status in {
            SupervisorStatus.STALE,
            SupervisorStatus.FAILED,
        }


@dataclass(frozen=True, slots=True)
class RestartDecision:
    """Worker再起動判定結果。"""

    should_restart: bool
    reason: SupervisorStopReason | None
    next_restart_at: datetime | None
    message: str | None = None

    def __post_init__(self) -> None:
        """再起動判定の整合性を検証する。"""

        if self.should_restart and self.reason is None:
            raise ValueError(
                "再起動判定には理由が必要です。"
            )

        if self.should_restart and self.next_restart_at is None:
            raise ValueError(
                "再起動判定には次回再起動日時が必要です。"
            )

        if not self.should_restart and self.next_restart_at is not None:
            raise ValueError(
                "再起動しない判定には日時を設定できません。"
            )
