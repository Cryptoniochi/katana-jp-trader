"""LineNotificationServiceのテスト。"""

import pytest

from app.notifications.line.line_exceptions import (
    LineDeliveryError,
)
from app.notifications.line.line_models import (
    LinePushMessageRequest,
    LineTextMessage,
)
from app.notifications.line.line_notification_service import (
    LineNotificationService,
)
from app.notifications.line.line_result import (
    LineDeliveryResult,
)
from app.notifications.webhook_models import (
    WebhookAttemptResult,
    WebhookDeliveryResult,
    WebhookResponse,
    WebhookRetryDecision,
)


def request() -> LinePushMessageRequest:
    return LinePushMessageRequest(
        destination_id="U1234567890",
        messages=(
            LineTextMessage(text="hello"),
        ),
    )


def line_result(
    *,
    succeeded: bool,
) -> LineDeliveryResult:
    status_code = 200 if succeeded else 400
    decision = (
        WebhookRetryDecision.SUCCEEDED
        if succeeded
        else WebhookRetryDecision.FAILED
    )
    error_message = None if succeeded else "bad request"

    return LineDeliveryResult(
        destination_id="U1234567890",
        delivery=WebhookDeliveryResult(
            url="https://api.line.me/v2/bot/message/push",
            attempts=(
                WebhookAttemptResult(
                    attempt_number=1,
                    decision=decision,
                    status_code=status_code,
                    error_message=error_message,
                ),
            ),
            response=WebhookResponse(
                status_code=status_code,
                body=(
                    "{}"
                    if succeeded
                    else '{"message":"invalid to"}'
                ),
            ),
        ),
    )


class FakeSender:
    def __init__(
        self,
        result: LineDeliveryResult,
    ) -> None:
        self.result = result
        self.raise_on_failure_values = []

    def send(
        self,
        request,
        *,
        raise_on_failure: bool = True,
    ) -> LineDeliveryResult:
        self.raise_on_failure_values.append(
            raise_on_failure
        )
        return self.result


def test_service_returns_success() -> None:
    sender = FakeSender(
        line_result(succeeded=True)
    )
    service = LineNotificationService(
        sender=sender
    )

    result = service.deliver(request())

    assert result.succeeded
    assert sender.raise_on_failure_values == [False]


def test_service_raises_line_delivery_error() -> None:
    sender = FakeSender(
        line_result(succeeded=False)
    )
    service = LineNotificationService(
        sender=sender
    )

    with pytest.raises(
        LineDeliveryError,
        match="invalid to",
    ) as raised:
        service.deliver(request())

    assert raised.value.api_error is not None
    assert raised.value.api_error.message == "invalid to"


def test_service_can_return_failure_without_raising() -> None:
    service = LineNotificationService(
        sender=FakeSender(
            line_result(succeeded=False)
        )
    )

    result = service.deliver(
        request(),
        raise_on_failure=False,
    )

    assert result.succeeded is False
