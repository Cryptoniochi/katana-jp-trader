"""Domain Eventを通知へ変換する購読ハンドラー。"""

from __future__ import annotations

from app.events.domain_events import (
    DomainEvent,
    DomainEventType,
)
from app.notifications.notification_models import (
    NotificationMessage,
    NotificationSeverity,
)
from app.notifications.notification_service import (
    NotificationService,
)


class NotificationSubscriber:
    """Domain Eventを通知メッセージへ変換して配信する。"""

    def __init__(
        self,
        *,
        service: NotificationService,
        event_types: frozenset[DomainEventType] | None = None,
    ) -> None:
        self.service = service
        self.event_types = (
            event_types
            if event_types is not None
            else frozenset(DomainEventType)
        )

    def __call__(self, event: DomainEvent) -> None:
        """Event Busハンドラーとして通知する。"""

        if event.event_type not in self.event_types:
            return

        notification = NotificationMessage(
            notification_id=event.event_id,
            title=self._title(event),
            body=self._body(event),
            severity=self._severity(event),
            created_at=event.occurred_at,
            source=event.source,
            metadata={
                "event_type": event.event_type.value,
                "correlation_id": event.correlation_id,
                **event.payload,
            },
        )
        self.service.deliver(notification)

    @staticmethod
    def _severity(
        event: DomainEvent,
    ) -> NotificationSeverity:
        if event.event_type is DomainEventType.ERROR_OCCURRED:
            return NotificationSeverity.ERROR

        if event.event_type is DomainEventType.RECOVERY_COMPLETED:
            if event.payload.get("has_errors"):
                return NotificationSeverity.WARNING

        if event.event_type is DomainEventType.RISK_ASSESSED:
            decision = event.payload.get("decision")
            if decision == "halted":
                return NotificationSeverity.CRITICAL
            if decision == "rejected":
                return NotificationSeverity.WARNING

        return NotificationSeverity.INFO

    @staticmethod
    def _title(event: DomainEvent) -> str:
        return event.event_type.value.replace("_", " ").title()

    @staticmethod
    def _body(event: DomainEvent) -> str:
        message = event.payload.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip()

        return (
            f"Domain event received: "
            f"{event.event_type.value}"
        )
