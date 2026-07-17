"""Discord Webhookへ通知を送信するチャネル。"""

from __future__ import annotations

from typing import Any

from app.notifications.discord_notification_models import (
    DiscordNotificationSettings,
)
from app.notifications.notification_models import (
    NotificationMessage,
    NotificationSeverity,
)
from app.notifications.webhook_client import WebhookClient
from app.notifications.webhook_models import WebhookRequest


class DiscordNotificationChannel:
    """NotificationMessageをDiscord Embedへ変換する。"""

    EMBED_COLORS = {
        NotificationSeverity.INFO: 0x3498DB,
        NotificationSeverity.WARNING: 0xF1C40F,
        NotificationSeverity.ERROR: 0xE74C3C,
        NotificationSeverity.CRITICAL: 0x9B59B6,
    }

    def __init__(
        self,
        *,
        settings: DiscordNotificationSettings,
        webhook_client: WebhookClient | None = None,
    ) -> None:
        self.settings = settings
        self.webhook_client = (
            webhook_client
            if webhook_client is not None
            else WebhookClient()
        )

    @property
    def channel_name(self) -> str:
        return "discord"

    def send(
        self,
        message: NotificationMessage,
    ) -> None:
        request = WebhookRequest(
            url=self.settings.webhook_url,
            payload=self._build_payload(message),
            headers={},
        )

        self.webhook_client.send(
            request,
            raise_on_failure=True,
        )

    def _build_payload(
        self,
        message: NotificationMessage,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "username": self.settings.username,
            "embeds": [
                {
                    "title": self._truncate(
                        message.title,
                        256,
                    ),
                    "description": self._truncate(
                        message.body,
                        4096,
                    ),
                    "color": self.EMBED_COLORS[
                        message.severity
                    ],
                    "timestamp": message.created_at.isoformat(),
                    "footer": {
                        "text": (
                            f"source={message.source} "
                            f"id={message.notification_id}"
                        )
                    },
                    "fields": self._build_fields(message),
                }
            ],
        }

        if self.settings.avatar_url is not None:
            payload["avatar_url"] = self.settings.avatar_url

        if self.settings.mention is not None:
            payload["content"] = self.settings.mention

        return payload

    def _build_fields(
        self,
        message: NotificationMessage,
    ) -> list[dict[str, Any]]:
        fields: list[dict[str, Any]] = [
            {
                "name": "Severity",
                "value": message.severity.value.upper(),
                "inline": True,
            },
            {
                "name": "Source",
                "value": self._truncate(
                    message.source,
                    1024,
                ),
                "inline": True,
            },
        ]

        preferred_keys = (
            "event_type",
            "code",
            "correlation_id",
            "current_status",
            "transition_type",
            "decision",
        )

        for key in preferred_keys:
            value = message.metadata.get(key)

            if value is None:
                continue

            fields.append(
                {
                    "name": key,
                    "value": self._truncate(
                        str(value),
                        1024,
                    ),
                    "inline": True,
                }
            )

        return fields[:25]

    @staticmethod
    def _truncate(
        value: str,
        limit: int,
    ) -> str:
        if len(value) <= limit:
            return value

        if limit <= 1:
            return value[:limit]

        return value[: limit - 1] + "…"
