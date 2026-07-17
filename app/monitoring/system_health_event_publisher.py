"""総合ヘルス状態変化をDomain Eventとして発行する。"""

from __future__ import annotations

from collections.abc import Callable
from uuid import uuid4

from app.events.domain_event_bus import DomainEventBus
from app.events.domain_events import (
    DomainEvent,
    DomainEventType,
)
from app.monitoring.system_health_transition import (
    SystemHealthTransition,
)


class SystemHealthEventPublisher:
    """総合ヘルス状態変化をDomain Event Busへ発行する。"""

    def __init__(
        self,
        *,
        event_bus: DomainEventBus,
        event_id_provider: Callable[[], str] | None = None,
        source: str = "system-health",
    ) -> None:
        """Event Bus・ID生成・発生元を設定する。"""

        normalized_source = source.strip()

        if not normalized_source:
            raise ValueError(
                "イベント発生元を指定してください。"
            )

        self.event_bus = event_bus
        self.event_id_provider = (
            event_id_provider
            if event_id_provider is not None
            else lambda: uuid4().hex
        )
        self.source = normalized_source

    def publish(
        self,
        transition: SystemHealthTransition,
        *,
        continue_on_error: bool = True,
    ):
        """状態変化をDomain Eventへ変換して配信する。"""

        event_id = self.event_id_provider().strip()

        if not event_id:
            raise ValueError(
                "イベントIDを生成できませんでした。"
            )

        event = DomainEvent(
            event_id=event_id,
            event_type=DomainEventType.ERROR_OCCURRED,
            occurred_at=transition.detected_at,
            source=self.source,
            correlation_id=(
                f"system-health-{transition.check_number}"
            ),
            payload={
                "message": transition.message,
                "severity": self._severity(transition),
                "transition_type": (
                    transition.transition_type.value
                ),
                "previous_status": (
                    transition.previous_status.value
                    if transition.previous_status is not None
                    else None
                ),
                "current_status": (
                    transition.current_status.value
                ),
                "check_number": transition.check_number,
                "reasons": list(
                    transition.current_report.reasons
                ),
                "update_health_status": (
                    transition.current_report
                    .update_health.status.value
                ),
                "runtime_error_rate": (
                    transition.current_report
                    .runtime_metrics.error_rate
                ),
                "notification_failure_rate": (
                    transition.current_report
                    .runtime_metrics
                    .notification_failure_rate
                ),
            },
        )

        return self.event_bus.publish(
            event,
            continue_on_error=continue_on_error,
        )

    @staticmethod
    def _severity(
        transition: SystemHealthTransition,
    ) -> str:
        """総合状態を通知・ログ用重大度へ変換する。"""

        status = transition.current_status.value

        if status == "critical":
            return "critical"

        if status == "degraded":
            return "error"

        if status == "warning":
            return "warning"

        return "info"
