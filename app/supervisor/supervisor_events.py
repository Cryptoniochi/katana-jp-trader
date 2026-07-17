"""Supervisor状態をDomain Eventへ変換する。"""

from __future__ import annotations

from collections.abc import Callable
from uuid import uuid4

from app.events.domain_event_bus import DomainEventBus
from app.events.domain_events import (
    DomainEvent,
    DomainEventType,
)
from app.supervisor.supervisor_models import (
    SupervisorSnapshot,
    SupervisorStatus,
)


class SupervisorEventPublisher:
    """Supervisor Snapshotを既存Domain Event Busへ発行する。"""

    def __init__(
        self,
        *,
        event_bus: DomainEventBus,
        event_id_provider: Callable[[], str] | None = None,
        source: str = "supervisor",
    ) -> None:
        """Event Bus・ID生成・発生元を設定する。"""

        source = source.strip()

        if not source:
            raise ValueError(
                "イベント発生元を指定してください。"
            )

        self.event_bus = event_bus
        self.event_id_provider = (
            event_id_provider
            if event_id_provider is not None
            else lambda: uuid4().hex
        )
        self.source = source

    def publish(
        self,
        snapshot: SupervisorSnapshot,
        *,
        continue_on_error: bool = True,
    ):
        """Supervisor状態をDomain Eventとして発行する。"""

        event_id = self.event_id_provider().strip()

        if not event_id:
            raise ValueError(
                "イベントIDを生成できませんでした。"
            )

        event = DomainEvent(
            event_id=event_id,
            event_type=DomainEventType.ERROR_OCCURRED,
            occurred_at=snapshot.checked_at,
            source=self.source,
            correlation_id=(
                f"supervisor-{snapshot.worker_name}"
            ),
            payload={
                "message": self._message(snapshot),
                "severity": self._severity(snapshot.status),
                "worker_name": snapshot.worker_name,
                "supervisor_status": snapshot.status.value,
                "restart_count": snapshot.restart_count,
                "uptime_seconds": snapshot.uptime_seconds,
                "heartbeat_age_seconds": (
                    snapshot.heartbeat_age_seconds
                ),
                "stop_reason": (
                    snapshot.stop_reason.value
                    if snapshot.stop_reason is not None
                    else None
                ),
            },
        )

        return self.event_bus.publish(
            event,
            continue_on_error=continue_on_error,
        )

    @staticmethod
    def _severity(
        status: SupervisorStatus,
    ) -> str:
        """Supervisor状態を通知用重大度へ変換する。"""

        if status is SupervisorStatus.FAILED:
            return "critical"

        if status is SupervisorStatus.STALE:
            return "error"

        if status is SupervisorStatus.RESTARTING:
            return "warning"

        return "info"

    @staticmethod
    def _message(
        snapshot: SupervisorSnapshot,
    ) -> str:
        """Supervisor通知メッセージを作成する。"""

        return (
            snapshot.message
            or (
                "Supervisor status changed: "
                f"worker={snapshot.worker_name} "
                f"status={snapshot.status.value}"
            )
        )
