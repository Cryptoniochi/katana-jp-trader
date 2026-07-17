"""Notification Gatewayの共通モデル。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.notifications.notification_models import (
    NotificationMessage,
    NotificationSeverity,
)
from app.notifications.notification_rule_models import (
    RuleBasedNotificationResult,
)
from app.notifications.notification_template import (
    NotificationTemplateName,
)


@dataclass(frozen=True, slots=True)
class NotificationGatewayRequest:
    """Gatewayへ渡す通知要求。"""

    notification_id: str
    template_name: NotificationTemplateName
    created_at: datetime
    source: str
    context: dict[str, Any]
    severity: NotificationSeverity | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """通知要求を検証して防御的コピーする。"""

        notification_id = self.notification_id.strip()
        source = self.source.strip()

        if not notification_id:
            raise ValueError(
                "通知IDを指定してください。"
            )

        if not source:
            raise ValueError(
                "通知発生元を指定してください。"
            )

        if self.created_at.tzinfo is None:
            raise ValueError(
                "通知作成日時にはタイムゾーンが必要です。"
            )

        if not isinstance(self.context, dict):
            raise TypeError(
                "通知Contextは辞書形式で指定してください。"
            )

        if not isinstance(self.metadata, dict):
            raise TypeError(
                "通知Metadataは辞書形式で指定してください。"
            )

        object.__setattr__(
            self,
            "notification_id",
            notification_id,
        )
        object.__setattr__(self, "source", source)
        object.__setattr__(
            self,
            "context",
            dict(self.context),
        )
        object.__setattr__(
            self,
            "metadata",
            dict(self.metadata),
        )


@dataclass(frozen=True, slots=True)
class NotificationGatewayResult:
    """Gatewayの通知処理結果。"""

    request: NotificationGatewayRequest
    notification: NotificationMessage
    routing_result: RuleBasedNotificationResult

    @property
    def delivered_count(self) -> int:
        """配信成功チャネル数を返す。"""

        delivery = self.routing_result.delivery

        if delivery is None:
            return 0

        return delivery.delivered_count

    @property
    def failed_count(self) -> int:
        """配信失敗チャネル数を返す。"""

        delivery = self.routing_result.delivery

        if delivery is None:
            return 0

        return delivery.failed_count

    @property
    def was_suppressed(self) -> bool:
        """通知ルールにより抑止されたか返す。"""

        return not self.routing_result.routing.should_deliver
