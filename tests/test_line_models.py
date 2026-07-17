"""LINE Messaging API共通モデルのテスト。"""

import pytest

from app.notifications.line.line_models import (
    LineDestinationType,
    LineNotificationSettings,
    LinePushMessageRequest,
    LineTextMessage,
)


def test_settings_normalizes_values_and_builds_url() -> None:
    settings = LineNotificationSettings(
        channel_access_token=" token-value ",
        destination_id=" U1234567890 ",
        destination_type=LineDestinationType.USER,
        api_base_url=" https://api.line.me/ ",
        timeout_seconds=5.0,
        maximum_attempts=4,
    )

    assert settings.channel_access_token == "token-value"
    assert settings.destination_id == "U1234567890"
    assert settings.push_message_url == (
        "https://api.line.me/v2/bot/message/push"
    )
    assert settings.timeout_seconds == 5.0
    assert settings.maximum_attempts == 4


def test_settings_rejects_destination_prefix_mismatch() -> None:
    with pytest.raises(
        ValueError,
        match="一致しません",
    ):
        LineNotificationSettings(
            channel_access_token="token",
            destination_id="C1234567890",
            destination_type=LineDestinationType.USER,
        )


def test_settings_masks_secrets() -> None:
    settings = LineNotificationSettings(
        channel_access_token="abcdefghij",
        destination_id="U1234567890",
    )

    summary = str(settings.masked_summary())

    assert "abcdefghij" not in summary
    assert "U1234567890" not in summary


def test_text_message_normalizes_and_builds_payload() -> None:
    message = LineTextMessage(
        text=" Project KATANA alert "
    )

    assert message.text == "Project KATANA alert"
    assert message.to_payload() == {
        "type": "text",
        "text": "Project KATANA alert",
    }


def test_text_message_rejects_empty_and_too_long() -> None:
    with pytest.raises(ValueError):
        LineTextMessage(text=" ")

    with pytest.raises(
        ValueError,
        match="5000",
    ):
        LineTextMessage(text="A" * 5001)


def test_push_request_builds_payload() -> None:
    request = LinePushMessageRequest(
        destination_id="U1234567890",
        messages=(
            LineTextMessage(text="first"),
            LineTextMessage(text="second"),
        ),
    )

    assert request.to_payload() == {
        "to": "U1234567890",
        "messages": [
            {
                "type": "text",
                "text": "first",
            },
            {
                "type": "text",
                "text": "second",
            },
        ],
    }


def test_push_request_rejects_more_than_five_messages() -> None:
    with pytest.raises(
        ValueError,
        match="5件",
    ):
        LinePushMessageRequest(
            destination_id="U1234567890",
            messages=tuple(
                LineTextMessage(text=f"message-{index}")
                for index in range(6)
            ),
        )
