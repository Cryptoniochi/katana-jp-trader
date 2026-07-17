"""LINE Messaging APIへPush Messageを送信する。"""

from __future__ import annotations

from app.notifications.line.line_client import (
    LineMessagingClient,
)
from app.notifications.line.line_models import (
    LinePushMessageRequest,
)
from app.notifications.line.line_result import (
    LineDeliveryResult,
)
from app.notifications.webhook_client import (
    WebhookClient,
)
from app.notifications.webhook_models import (
    WebhookDeliveryResult,
)


class LineMessagingSender:
    """既存Webhook Clientを使ってLINE通知を送信する。"""

    def __init__(
        self,
        *,
        client: LineMessagingClient,
        webhook_client: WebhookClient | None = None,
    ) -> None:
        """LINE ClientとWebhook Clientを設定する。"""

        self.client = client
        self.webhook_client = (
            webhook_client
            if webhook_client is not None
            else WebhookClient(
                policy=client.retry_policy
            )
        )

    def send(
        self,
        request: LinePushMessageRequest,
        *,
        raise_on_failure: bool = True,
    ) -> LineDeliveryResult:
        """LINE Push Message APIへ送信する。"""

        webhook_request = (
            self.client.build_push_request(request)
        )
        delivery = self.webhook_client.send(
            webhook_request,
            raise_on_failure=raise_on_failure,
        )

        return LineDeliveryResult(
            destination_id=request.destination_id,
            delivery=delivery,
        )
