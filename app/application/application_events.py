"""Application Orchestrator結果をDomain Eventへ変換する。"""

from __future__ import annotations

from collections.abc import Callable
from uuid import uuid4

from app.application.application_orchestrator import (
    ApplicationOrchestrationResult,
    ApplicationShutdownResult,
)
from app.events.domain_event_bus import DomainEventBus
from app.events.domain_events import (
    DomainEvent,
    DomainEventType,
)


class ApplicationEventPublisher:
    """Application Lifecycle結果をDomain Event Busへ発行する。"""

    def __init__(
        self,
        *,
        event_bus: DomainEventBus,
        event_id_provider: Callable[[], str] | None = None,
        source: str = "application-orchestrator",
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

    def publish_started(
        self,
        result: ApplicationOrchestrationResult,
        *,
        continue_on_error: bool = True,
    ):
        """Application開始結果を発行する。"""

        return self._publish(
            occurred_at=result.application.checked_at,
            state=result.application.state.value,
            has_errors=result.has_failures,
            components=result.components,
            lifecycle_action="started",
            message="Application startup completed.",
            continue_on_error=continue_on_error,
        )

    def publish_stopped(
        self,
        result: ApplicationShutdownResult,
        *,
        continue_on_error: bool = True,
    ):
        """Application停止結果を発行する。"""

        snapshot = result.application_report.snapshot

        return self._publish(
            occurred_at=snapshot.checked_at,
            state=snapshot.state.value,
            has_errors=result.has_failures,
            components=result.components,
            lifecycle_action="stopped",
            message="Application shutdown completed.",
            continue_on_error=continue_on_error,
        )

    def _publish(
        self,
        *,
        occurred_at,
        state: str,
        has_errors: bool,
        components,
        lifecycle_action: str,
        message: str,
        continue_on_error: bool,
    ):
        """既存Domain Event種別でLifecycle結果を発行する。"""

        event_id = self.event_id_provider().strip()

        if not event_id:
            raise ValueError(
                "イベントIDを生成できませんでした。"
            )

        event = DomainEvent(
            event_id=event_id,
            event_type=DomainEventType.RECOVERY_COMPLETED,
            occurred_at=occurred_at,
            source=self.source,
            correlation_id="application-lifecycle",
            payload={
                "message": message,
                "has_errors": has_errors,
                "lifecycle_action": lifecycle_action,
                "application_state": state,
                "components": [
                    {
                        "component_name": item.component_name,
                        "state": item.state.value,
                        "start_order": item.start_order,
                        "stop_order": item.stop_order,
                        "error_message": item.error_message,
                    }
                    for item in components
                ],
            },
        )

        return self.event_bus.publish(
            event,
            continue_on_error=continue_on_error,
        )
