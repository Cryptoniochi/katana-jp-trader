"""Project KATANA Service Managerの共通モデル。"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any


class ManagedComponentName(StrEnum):
    """Service Managerが管理するコンポーネント。"""

    DASHBOARD = "dashboard"
    PAPER_TRADING = "paper_trading"
    PAPER_TRADING_SCHEDULER = "paper_trading_scheduler"
    DAILY_REPORT_SCHEDULER = "daily_report_scheduler"
    DYNAMIC_WATCHLIST_SCHEDULER = "dynamic_watchlist_scheduler"
    UNIVERSE_DAILY_SCHEDULER = "universe_daily_scheduler"
    MORNING_PREFLIGHT_SCHEDULER = "morning_preflight_scheduler"


class ManagedComponentState(StrEnum):
    """管理対象プロセスの状態。"""

    DISABLED = "disabled"
    STARTING = "starting"
    RUNNING = "running"
    STOPPED = "stopped"
    FAILED = "failed"
    RESTART_WAIT = "restart_wait"


class ServiceEventType(StrEnum):
    """Service Managerの運用イベント種別。"""

    SERVICE_STARTED = "service_started"
    SERVICE_STOPPING = "service_stopping"
    COMPONENT_STARTED = "component_started"
    COMPONENT_STOPPED = "component_stopped"
    COMPONENT_FAILED = "component_failed"
    RESTART_SCHEDULED = "restart_scheduled"
    RESTART_COMPLETED = "restart_completed"
    READINESS_CHANGED = "readiness_changed"


@dataclass(frozen=True, slots=True)
class ServiceEvent:
    """Dashboardへ表示する運用イベント。"""

    occurred_at: datetime
    event_type: ServiceEventType
    component: ManagedComponentName | None
    message: str

    def __post_init__(self) -> None:
        if self.occurred_at.tzinfo is None:
            raise ValueError(
                "イベント日時にはタイムゾーンが必要です。"
            )

        if not self.message.strip():
            raise ValueError(
                "イベントメッセージを指定してください。"
            )

        object.__setattr__(
            self,
            "message",
            self.message.strip(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "occurred_at": self.occurred_at.isoformat(),
            "event_type": self.event_type.value,
            "component": (
                self.component.value
                if self.component is not None
                else None
            ),
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class ManagedComponentStatus:
    """1コンポーネントの現在状態。"""

    name: ManagedComponentName
    state: ManagedComponentState
    enabled: bool
    process_id: int | None
    restart_count: int
    last_exit_code: int | None
    started_at: datetime | None
    updated_at: datetime
    message: str | None = None

    def __post_init__(self) -> None:
        if self.restart_count < 0:
            raise ValueError(
                "再起動回数は0以上である必要があります。"
            )

        if self.started_at is not None and (
            self.started_at.tzinfo is None
        ):
            raise ValueError(
                "起動日時にはタイムゾーンが必要です。"
            )

        if self.updated_at.tzinfo is None:
            raise ValueError(
                "更新日時にはタイムゾーンが必要です。"
            )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["name"] = self.name.value
        payload["state"] = self.state.value
        payload["started_at"] = (
            self.started_at.isoformat()
            if self.started_at is not None
            else None
        )
        payload["updated_at"] = (
            self.updated_at.isoformat()
        )
        return payload


@dataclass(frozen=True, slots=True)
class KatanaServiceStatus:
    """Service Manager全体の状態。"""

    generated_at: datetime
    service_state: str
    kabu_station_readiness: str
    components: tuple[ManagedComponentStatus, ...]
    service_started_at: datetime | None = None
    uptime_seconds: float | None = None
    recent_events: tuple[ServiceEvent, ...] = ()

    def __post_init__(self) -> None:
        if self.generated_at.tzinfo is None:
            raise ValueError(
                "生成日時にはタイムゾーンが必要です。"
            )

        if (
            self.service_started_at is not None
            and self.service_started_at.tzinfo is None
        ):
            raise ValueError(
                "Service起動日時にはタイムゾーンが必要です。"
            )

        if (
            self.uptime_seconds is not None
            and self.uptime_seconds < 0
        ):
            raise ValueError(
                "稼働時間は0以上である必要があります。"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": (
                self.generated_at.isoformat()
            ),
            "service_state": self.service_state,
            "kabu_station_readiness": (
                self.kabu_station_readiness
            ),
            "service_started_at": (
                self.service_started_at.isoformat()
                if self.service_started_at is not None
                else None
            ),
            "uptime_seconds": self.uptime_seconds,
            "components": [
                item.to_dict()
                for item in self.components
            ],
            "recent_events": [
                item.to_dict()
                for item in self.recent_events
            ],
        }
