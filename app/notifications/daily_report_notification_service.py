"""Daily Trading Reportを既存通知Gatewayへ配信する。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Protocol
from uuid import uuid4

from app.notifications.daily_report_formatter import (
    DailyReportNotificationContent,
    DailyReportNotificationFormatter,
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


class DailyReportSource(Protocol):
    """日次レポートReaderの最小Protocol。"""

    def read_latest(
        self,
    ) -> dict[str, Any]:
        """最新レポートを返す。"""

    def read_for_date(
        self,
        report_date: date,
    ) -> dict[str, Any]:
        """指定日のレポートを返す。"""


class NotificationGatewaySender(Protocol):
    """Daily Reportが利用するGateway Protocol。"""

    def send(
        self,
        request: NotificationGatewayRequest,
        *,
        continue_on_error: bool = True,
    ) -> NotificationGatewayResult:
        """通知要求を送信する。"""


@dataclass(frozen=True, slots=True)
class DailyReportNotificationResult:
    """日次レポート通知の実行結果。"""

    payload: dict[str, Any]
    content: DailyReportNotificationContent
    gateway_result: NotificationGatewayResult

    @property
    def delivered_count(self) -> int:
        return (
            self.gateway_result.delivered_count
        )

    @property
    def failed_count(self) -> int:
        return self.gateway_result.failed_count


class DailyReportNotificationService:
    """Daily Report ReaderとNotification Gatewayを接続する。"""

    def __init__(
        self,
        *,
        reader: DailyReportSource,
        gateway: NotificationGatewaySender,
        formatter: DailyReportNotificationFormatter | None = None,
    ) -> None:
        self.reader = reader
        self.gateway = gateway
        self.formatter = (
            formatter
            if formatter is not None
            else DailyReportNotificationFormatter()
        )

    def send_latest(
        self,
        *,
        created_at: datetime | None = None,
        continue_on_error: bool = True,
    ) -> DailyReportNotificationResult:
        """最新の日次レポートを通知する。"""

        return self._send_payload(
            self.reader.read_latest(),
            created_at=created_at,
            continue_on_error=continue_on_error,
        )

    def send_for_date(
        self,
        report_date: date,
        *,
        created_at: datetime | None = None,
        continue_on_error: bool = True,
    ) -> DailyReportNotificationResult:
        """指定日の日次レポートを通知する。"""

        return self._send_payload(
            self.reader.read_for_date(
                report_date
            ),
            created_at=created_at,
            continue_on_error=continue_on_error,
        )

    def _send_payload(
        self,
        payload: dict[str, Any],
        *,
        created_at: datetime | None,
        continue_on_error: bool,
    ) -> DailyReportNotificationResult:
        resolved_created_at = (
            created_at
            if created_at is not None
            else datetime.now(timezone.utc)
        )

        if resolved_created_at.tzinfo is None:
            raise ValueError(
                "通知作成日時にはタイムゾーンが必要です。"
            )

        content = self.formatter.format(
            payload
        )
        report_date = (
            payload.get("report_date")
            or "latest"
        )
        request = NotificationGatewayRequest(
            notification_id=(
                "daily-report-"
                f"{report_date}-"
                f"{uuid4().hex[:12]}"
            ),
            template_name=(
                NotificationTemplateName.GENERIC
            ),
            created_at=resolved_created_at,
            source="daily_report",
            context={
                "title": content.title,
                "message": content.body,
            },
            severity=NotificationSeverity.INFO,
            metadata=content.metadata,
        )
        gateway_result = self.gateway.send(
            request,
            continue_on_error=continue_on_error,
        )

        return DailyReportNotificationResult(
            payload=payload,
            content=content,
            gateway_result=gateway_result,
        )
