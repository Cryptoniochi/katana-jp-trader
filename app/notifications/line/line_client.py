"""LINE Push Message API要求を構築するClient基盤。"""

from __future__ import annotations

from app.notifications.line.line_models import (
    LineNotificationSettings,
    LinePushMessageRequest,
)
from app.notifications.webhook_models import (
    WebhookRequest,
    WebhookRetryPolicy,
)


class LineMessagingClient:
    """LINE Messaging APIの送信要求と再試行条件を構築する。"""

    def __init__(
        self,
        *,
        settings: LineNotificationSettings,
    ) -> None:
        """LINE設定を保持する。"""

        self.settings = settings

    @property
    def retry_policy(self) -> WebhookRetryPolicy:
        """既存Webhook Client用の再試行条件を返す。"""

        return WebhookRetryPolicy(
            maximum_attempts=self.settings.maximum_attempts,
            timeout_seconds=self.settings.timeout_seconds,
        )

    def build_push_request(
        self,
        request: LinePushMessageRequest,
    ) -> WebhookRequest:
        """LINE Push Message API用WebhookRequestを作成する。"""

        if request.destination_id != self.settings.destination_id:
            raise ValueError(
                "LINE送信要求の宛先が設定済み宛先と一致しません。"
            )

        return WebhookRequest(
            url=self.settings.push_message_url,
            payload=request.to_payload(),
            headers={
                "Authorization": (
                    "Bearer "
                    f"{self.settings.channel_access_token}"
                ),
            },
        )
