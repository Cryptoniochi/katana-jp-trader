"""NotificationMessageをLINE Messaging APIへ送信するチャネル。"""

from __future__ import annotations

from app.notifications.line.line_models import (
    LineNotificationSettings,
    LinePushMessageRequest,
    LineTextMessage,
)
from app.notifications.line.line_notification_service import (
    LineNotificationService,
)
from app.notifications.notification_models import (
    NotificationMessage,
    NotificationSeverity,
)


class LineNotificationChannel:
    """既存NotificationChannelとして利用できるLINE実装。"""

    SEVERITY_SYMBOLS = {
        NotificationSeverity.INFO: "ℹ️",
        NotificationSeverity.WARNING: "⚠️",
        NotificationSeverity.ERROR: "❌",
        NotificationSeverity.CRITICAL: "🚨",
    }

    def __init__(
        self,
        *,
        settings: LineNotificationSettings,
        service: LineNotificationService,
    ) -> None:
        """LINE設定と送信Serviceを保持する。"""

        self.settings = settings
        self.service = service

    @property
    def channel_name(self) -> str:
        """NotificationChannel名を返す。"""

        return "line"

    def send(
        self,
        message: NotificationMessage,
    ) -> None:
        """NotificationMessageをLINE Text Messageへ変換して送る。"""

        request = LinePushMessageRequest(
            destination_id=self.settings.destination_id,
            messages=(
                LineTextMessage(
                    text=self._format_text(message)
                ),
            ),
        )

        self.service.deliver(
            request,
            raise_on_failure=True,
        )

    def _format_text(
        self,
        message: NotificationMessage,
    ) -> str:
        """LINE表示用本文を作成する。"""

        symbol = self.SEVERITY_SYMBOLS[
            message.severity
        ]
        metadata_lines = self._metadata_lines(message)

        sections = [
            (
                f"{symbol} "
                f"[{message.severity.value.upper()}] "
                f"{message.title}"
            ),
            message.body,
        ]

        if metadata_lines:
            sections.append(
                "\n".join(metadata_lines)
            )

        sections.append(
            (
                f"source={message.source}\n"
                f"id={message.notification_id}\n"
                f"time={message.created_at.isoformat()}"
            )
        )

        text = "\n\n".join(sections)

        if len(text) <= 5000:
            return text

        return text[:4999] + "…"

    @staticmethod
    def _metadata_lines(
        message: NotificationMessage,
    ) -> tuple[str, ...]:
        """重要MetadataをLINE表示用へ変換する。"""

        preferred_keys = (
            "event_type",
            "code",
            "correlation_id",
            "current_status",
            "transition_type",
            "decision",
            "worker_name",
            "restart_count",
            "consecutive_failure_count",
        )

        lines: list[str] = []

        for key in preferred_keys:
            value = message.metadata.get(key)

            if value is None:
                continue

            lines.append(f"{key}={value}")

        return tuple(lines)
