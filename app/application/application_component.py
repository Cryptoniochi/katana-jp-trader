"""Application Orchestratorで管理するComponentモデル。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable


class ApplicationComponentState(StrEnum):
    """Application Componentの状態。"""

    REGISTERED = "registered"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"


@runtime_checkable
class ApplicationComponent(Protocol):
    """Orchestratorが管理するComponentの共通インターフェース。"""

    @property
    def component_name(self) -> str:
        """Component名を返す。"""

    def start(self) -> None:
        """Componentを開始する。"""

    def stop(self) -> None:
        """Componentを停止する。"""


@dataclass(frozen=True, slots=True)
class ApplicationComponentSnapshot:
    """1つのComponentの現在状態。"""

    component_name: str
    state: ApplicationComponentState
    start_order: int
    stop_order: int
    error_message: str | None = None

    def __post_init__(self) -> None:
        """Component状態を検証して正規化する。"""

        component_name = self.component_name.strip()
        error_message = (
            None
            if self.error_message is None
            else self.error_message.strip() or None
        )

        if not component_name:
            raise ValueError(
                "Application Component名を指定してください。"
            )

        if self.start_order < 0:
            raise ValueError(
                "開始順序は0以上である必要があります。"
            )

        if self.stop_order < 0:
            raise ValueError(
                "停止順序は0以上である必要があります。"
            )

        if (
            self.state is ApplicationComponentState.FAILED
            and error_message is None
        ):
            raise ValueError(
                "FAILED状態にはエラーメッセージが必要です。"
            )

        if (
            self.state is not ApplicationComponentState.FAILED
            and error_message is not None
        ):
            raise ValueError(
                "FAILED以外の状態にはエラーを設定できません。"
            )

        object.__setattr__(
            self,
            "component_name",
            component_name,
        )
        object.__setattr__(
            self,
            "error_message",
            error_message,
        )


@dataclass(frozen=True, slots=True)
class ApplicationComponentRegistration:
    """Orchestratorへ登録するComponent設定。"""

    component: ApplicationComponent
    start_order: int
    stop_order: int | None = None

    def __post_init__(self) -> None:
        """登録情報を検証する。"""

        component_name = self.component.component_name.strip()

        if not component_name:
            raise ValueError(
                "Application Component名を指定してください。"
            )

        if self.start_order < 0:
            raise ValueError(
                "開始順序は0以上である必要があります。"
            )

        resolved_stop_order = (
            self.start_order
            if self.stop_order is None
            else self.stop_order
        )

        if resolved_stop_order < 0:
            raise ValueError(
                "停止順序は0以上である必要があります。"
            )

        object.__setattr__(
            self,
            "stop_order",
            resolved_stop_order,
        )

    @property
    def component_name(self) -> str:
        """登録Component名を返す。"""

        return self.component.component_name.strip()
