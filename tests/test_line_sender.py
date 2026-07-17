"""LineMessagingSenderのテスト。"""

from app.notifications.line.line_client import (
    LineMessagingClient,
)
from app.notifications.line.line_models import (
    LineNotificationSettings,
    LinePushMessageRequest,
    LineTextMessage,
)
from app.notifications.line.line_sender import (
    LineMessagingSender,
)
from app.notifications.webhook_models import (
    WebhookAttemptResult,
    WebhookDeliveryResult,
    WebhookResponse,
    WebhookRetryDecision,
)


class FakeWebhookClient:
    def __init__(
        self,
        result: WebhookDeliveryResult,
    ) -> None:
        self.result = result
        self.requests = []
        self.raise_on_failure_values = []

    def send(
        self,
        request,
        *,
        raise_on_failure: bool = True,
    ) -> WebhookDeliveryResult:
        self.requests.append(request)
        self.raise_on_failure_values.append(
            raise_on_failure
        )
        return self.result


def settings() -> LineNotificationSettings:
    return LineNotificationSettings(
        channel_access_token="secret-token",
        destination_id="U1234567890",
        timeout_seconds=5.0,
        maximum_attempts=3,
    )


def success_delivery() -> WebhookDeliveryResult:
    return WebhookDeliveryResult(
        url="https://api.line.me/v2/bot/message/push",
        attempts=(
            WebhookAttemptResult(
                attempt_number=1,
                decision=WebhookRetryDecision.SUCCEEDED,
                status_code=200,
                error_message=None,
            ),
        ),
        response=WebhookResponse(
            status_code=200,
            body="{}",
        ),
    )


def test_sender_uses_webhook_client() -> None:
    fake = FakeWebhookClient(
        success_delivery()
    )
    sender = LineMessagingSender(
        client=LineMessagingClient(
            settings=settings()
        ),
        webhook_client=fake,
    )
    request = LinePushMessageRequest(
        destination_id="U1234567890",
        messages=(
            LineTextMessage(text="hello"),
        ),
    )

    result = sender.send(
        request,
        raise_on_failure=False,
    )

    assert result.succeeded
    assert result.attempt_count == 1
    assert fake.raise_on_failure_values == [False]
    assert fake.requests[0].headers == {
        "Authorization": "Bearer secret-token",
    }


def test_sender_returns_failed_result() -> None:
    delivery = WebhookDeliveryResult(
        url="https://api.line.me/v2/bot/message/push",
        attempts=(
            WebhookAttemptResult(
                attempt_number=1,
                decision=WebhookRetryDecision.FAILED,
                status_code=400,
                error_message="bad request",
            ),
        ),
        response=WebhookResponse(
            status_code=400,
            body='{"message":"invalid to"}',
        ),
    )
    sender = LineMessagingSender(
        client=LineMessagingClient(
            settings=settings()
        ),
        webhook_client=FakeWebhookClient(delivery),
    )

    result = sender.send(
        LinePushMessageRequest(
            destination_id="U1234567890",
            messages=(
                LineTextMessage(text="hello"),
            ),
        ),
        raise_on_failure=False,
    )

    assert result.succeeded is False
    assert result.attempt_count == 1
