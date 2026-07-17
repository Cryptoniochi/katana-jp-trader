"""通知テンプレートとルール配信を統合するGateway。"""

from __future__ import annotations

from typing import Protocol

from app.notifications.notification_gateway_models import (
    NotificationGatewayRequest,
    NotificationGatewayResult,
)
from app.notifications.notification_models import NotificationMessage
from app.notifications.notification_rule_models import (
    RuleBasedNotificationResult,
)
from app.notifications.notification_template import (
    NotificationTemplateRegistry,
)


class RuleBasedNotificationSender(Protocol):
    """Gatewayが利用するルールベース通知送信処理。"""

    def deliver(
        self,
        notification: NotificationMessage,
        *,
        continue_on_error: bool = True,
    ) -> RuleBasedNotificationResult:
        """通知をルール評価後に配信する。"""


class NotificationResultObserver(Protocol):
    """通知結果を記録する任意Observer。"""

    def record(
        self,
        result,
    ) -> None:
        """通知結果を記録する。"""


class NotificationGateway:
    """テンプレート描画・通知生成・ルーティングを一元化する。"""

    def __init__(
        self,
        *,
        sender: RuleBasedNotificationSender,
        template_registry: NotificationTemplateRegistry | None = None,
        observers: tuple[NotificationResultObserver, ...] = (),
    ) -> None:
        """送信処理・テンプレート・結果Observerを設定する。"""

        self.sender = sender
        self.template_registry = (
            template_registry
            if template_registry is not None
            else NotificationTemplateRegistry()
        )
        self.observers = observers

    def send(
        self,
        request: NotificationGatewayRequest,
        *,
        continue_on_error: bool = True,
    ) -> NotificationGatewayResult:
        """通知要求を描画し、ルールに従って配信する。"""

        template = self.template_registry.get(
            request.template_name
        )
        title, body = template.render(request.context)
        severity = request.severity or template.default_severity

        notification = NotificationMessage(
            notification_id=request.notification_id,
            title=title,
            body=body,
            severity=severity,
            created_at=request.created_at,
            source=request.source,
            metadata={
                "template_name": request.template_name.value,
                **request.metadata,
            },
        )

        routing_result = self.sender.deliver(
            notification,
            continue_on_error=continue_on_error,
        )

        delivery = routing_result.delivery

        if delivery is not None:
            for observer in self.observers:
                observer.record(delivery)

        return NotificationGatewayResult(
            request=request,
            notification=notification,
            routing_result=routing_result,
        )
