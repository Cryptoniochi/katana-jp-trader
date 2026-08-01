"""Morning Pre-Flightを既存通知Gatewayへ配信する。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol
from uuid import uuid4

from app.notifications.morning_preflight_formatter import (
    MorningPreflightNotificationContent,
    MorningPreflightNotificationFormatter,
)
from app.notifications.notification_gateway_models import (
    NotificationGatewayRequest,
    NotificationGatewayResult,
)
from app.notifications.notification_models import (
    NotificationSeverity,
)
from app.notifications.notification_template import (
    NotificationTemplateName,
)


class MorningPreflightSource(Protocol):
    """Morning Pre-Flight結果Source。"""

    def evaluate(
        self,
    ) -> Any:
        """自律運転検証Reportを返す。"""


class NotificationGatewaySender(Protocol):
    """通知Gateway Protocol。"""

    def send(
        self,
        request: NotificationGatewayRequest,
        *,
        continue_on_error: bool = True,
    ) -> NotificationGatewayResult:
        """通知要求を送信する。"""


@dataclass(frozen=True, slots=True)
class MorningPreflightNotificationResult:
    """Morning Pre-Flight通知結果。"""

    payload: dict[str, Any]
    content: MorningPreflightNotificationContent
    gateway_result: NotificationGatewayResult

    @property
    def delivered_count(self) -> int:
        return self.gateway_result.delivered_count

    @property
    def failed_count(self) -> int:
        return self.gateway_result.failed_count


class MorningPreflightNotificationService:
    """ValidatorとNotification Gatewayを接続する。"""

    def __init__(
        self,
        *,
        validator: MorningPreflightSource,
        gateway: NotificationGatewaySender,
        formatter: MorningPreflightNotificationFormatter | None = None,
    ) -> None:
        self.validator = validator
        self.gateway = gateway
        self.formatter = (
            formatter
            if formatter is not None
            else MorningPreflightNotificationFormatter()
        )

    def send(
        self,
        *,
        created_at: datetime | None = None,
        continue_on_error: bool = True,
    ) -> MorningPreflightNotificationResult:
        """Morning Pre-Flightを評価し通知する。"""

        report = self.validator.evaluate()
        payload = (
            report.to_dict()
            if hasattr(report, "to_dict")
            else dict(report)
        )
        content = self.formatter.format(payload)
        resolved_created_at = (
            created_at
            if created_at is not None
            else datetime.now(timezone.utc)
        )

        if resolved_created_at.tzinfo is None:
            raise ValueError(
                "通知作成日時にはタイムゾーンが必要です。"
            )

        severity = (
            NotificationSeverity.INFO
            if payload.get(
                "ready_for_next_business_day",
                False,
            )
            else NotificationSeverity.ERROR
        )
        request = NotificationGatewayRequest(
            notification_id=(
                "morning-preflight-"
                f"{uuid4().hex[:12]}"
            ),
            template_name=(
                NotificationTemplateName.GENERIC
            ),
            created_at=resolved_created_at,
            source="morning_preflight",
            context={
                "title": content.title,
                "message": content.body,
            },
            severity=severity,
            metadata=content.metadata,
        )
        gateway_result = self.gateway.send(
            request,
            continue_on_error=continue_on_error,
        )

        return MorningPreflightNotificationResult(
            payload=payload,
            content=content,
            gateway_result=gateway_result,
        )
