"""LineMessagingClientのテスト。"""

import pytest

from app.notifications.line.line_client import (
    LineMessagingClient,
)
from app.notifications.line.line_models import (
    LineNotificationSettings,
    LinePushMessageRequest,
    LineTextMessage,
)


def settings() -> LineNotificationSettings:
    return LineNotificationSettings(
        channel_access_token="secret-token",
        destination_id="U1234567890",
        timeout_seconds=7.5,
        maximum_attempts=4,
    )


def test_client_builds_authorized_push_request() -> None:
    client = LineMessagingClient(
        settings=settings()
    )
    push_request = LinePushMessageRequest(
        destination_id="U1234567890",
        messages=(
            LineTextMessage(text="hello"),
        ),
    )

    request = client.build_push_request(
        push_request
    )

    assert request.url == (
        "https://api.line.me/v2/bot/message/push"
    )
    assert request.payload == {
        "to": "U1234567890",
        "messages": [
            {
                "type": "text",
                "text": "hello",
            },
        ],
    }
    assert request.headers == {
        "Authorization": "Bearer secret-token",
    }


def test_client_builds_retry_policy_from_settings() -> None:
    client = LineMessagingClient(
        settings=settings()
    )

    policy = client.retry_policy

    assert policy.maximum_attempts == 4
    assert policy.timeout_seconds == 7.5


def test_client_rejects_unconfigured_destination() -> None:
    client = LineMessagingClient(
        settings=settings()
    )
    push_request = LinePushMessageRequest(
        destination_id="U9999999999",
        messages=(
            LineTextMessage(text="hello"),
        ),
    )

    with pytest.raises(
        ValueError,
        match="一致しません",
    ):
        client.build_push_request(
            push_request
        )
