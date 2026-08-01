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


class ManagedComponentState(StrEnum):
    """管理対象プロセスの状態。"""

    DISABLED = "disabled"
    STARTING = "starting"
    RUNNING = "running"
    STOPPED = "stopped"
    FAILED = "failed"
    RESTART_WAIT = "restart_wait"


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

    def __post_init__(self) -> None:
        if self.generated_at.tzinfo is None:
            raise ValueError(
                "生成日時にはタイムゾーンが必要です。"
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
            "components": [
                item.to_dict()
                for item in self.components
            ],
        }
