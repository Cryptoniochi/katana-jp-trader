"""Slack Incoming Webhookへ通知を送信するチャネル。"""

from __future__ import annotations

from typing import Any

from app.notifications.notification_models import (
    NotificationMessage,
    NotificationSeverity,
)
from app.notifications.slack_notification_models import (
    SlackNotificationSettings,
)
from app.notifications.webhook_client import WebhookClient
from app.notifications.webhook_models import WebhookRequest


class SlackNotificationChannel:
    """NotificationMessageをSlack Block Kitへ変換する。"""

    SEVERITY_SYMBOLS = {
        NotificationSeverity.INFO: "ℹ️",
        NotificationSeverity.WARNING: "⚠️",
        NotificationSeverity.ERROR: "❌",
        NotificationSeverity.CRITICAL: "🚨",
    }

    def __init__(
        self,
        *,
        settings: SlackNotificationSettings,
        webhook_client: WebhookClient | None = None,
    ) -> None:
        """Slack設定とWebhook Clientを設定する。"""

        self.settings = settings
        self.webhook_client = (
            webhook_client
            if webhook_client is not None
            else WebhookClient()
        )

    @property
    def channel_name(self) -> str:
        """NotificationChannel名を返す。"""

        return "slack"

    def send(
        self,
        message: NotificationMessage,
    ) -> None:
        """Slack Incoming Webhookへ通知を送信する。"""

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
        """Slack Block Kit Payloadを作成する。"""

        symbol = self.SEVERITY_SYMBOLS[
            message.severity
        ]

        payload: dict[str, Any] = {
            "username": self.settings.username,
            "text": self._fallback_text(
                message,
                symbol=symbol,
            ),
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": self._truncate(
                            f"{symbol} {message.title}",
                            150,
                        ),
                        "emoji": True,
                    },
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": self._truncate(
                            message.body,
                            3000,
                        ),
                    },
                },
                {
                    "type": "section",
                    "fields": self._build_fields(
                        message
                    ),
                },
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": self._truncate(
                                (
                                    f"*source:* {message.source}  "
                                    f"*id:* {message.notification_id}  "
                                    f"*time:* "
                                    f"{message.created_at.isoformat()}"
                                ),
                                3000,
                            ),
                        }
                    ],
                },
            ],
        }

        if self.settings.icon_emoji is not None:
            payload["icon_emoji"] = (
                self.settings.icon_emoji
            )

        if self.settings.channel is not None:
            payload["channel"] = self.settings.channel

        if self.settings.mention is not None:
            payload["blocks"].insert(
                0,
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": self.settings.mention,
                    },
                },
            )

        return payload

    def _build_fields(
        self,
        message: NotificationMessage,
    ) -> list[dict[str, str]]:
        """MetadataからSlack Fieldsを作成する。"""

        fields: list[dict[str, str]] = [
            {
                "type": "mrkdwn",
                "text": (
                    f"*Severity*\n"
                    f"{message.severity.value.upper()}"
                ),
            },
            {
                "type": "mrkdwn",
                "text": (
                    f"*Source*\n"
                    f"{self._escape_mrkdwn(message.source)}"
                ),
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
                    "type": "mrkdwn",
                    "text": self._truncate(
                        (
                            f"*{key}*\n"
                            f"{self._escape_mrkdwn(str(value))}"
                        ),
                        2000,
                    ),
                }
            )

        return fields[:10]

    @staticmethod
    def _fallback_text(
        message: NotificationMessage,
        *,
        symbol: str,
    ) -> str:
        """Block Kit非対応環境向けテキストを返す。"""

        return (
            f"{symbol} [{message.severity.value.upper()}] "
            f"{message.title}: {message.body}"
        )

    @staticmethod
    def _escape_mrkdwn(value: str) -> str:
        """Slack mrkdwnの特殊文字をエスケープする。"""

        return (
            value.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

    @staticmethod
    def _truncate(
        value: str,
        limit: int,
    ) -> str:
        """Slackの文字数制限へ収まるよう切り詰める。"""

        if len(value) <= limit:
            return value

        if limit <= 1:
            return value[:limit]

        return value[: limit - 1] + "…"
