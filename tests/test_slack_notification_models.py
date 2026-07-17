"""SlackNotificationSettingsのテスト。"""

import pytest

from app.notifications.slack_notification_models import (
    SlackNotificationSettings,
)


def test_settings_normalizes_values() -> None:
    settings = SlackNotificationSettings(
        webhook_url=" https://hooks.slack.test/services/1 ",
        username=" KATANA ",
        icon_emoji=" :robot_face: ",
        channel=" #alerts ",
        mention=" <!channel> ",
    )

    assert settings.webhook_url == (
        "https://hooks.slack.test/services/1"
    )
    assert settings.username == "KATANA"
    assert settings.icon_emoji == ":robot_face:"
    assert settings.channel == "#alerts"
    assert settings.mention == "<!channel>"


def test_settings_rejects_invalid_values() -> None:
    with pytest.raises(ValueError, match="Webhook URL"):
        SlackNotificationSettings(
            webhook_url=" ",
        )

    with pytest.raises(ValueError, match="http"):
        SlackNotificationSettings(
            webhook_url="hooks.slack.test/services/1",
        )

    with pytest.raises(ValueError, match="絵文字"):
        SlackNotificationSettings(
            webhook_url="https://hooks.slack.test/services/1",
            icon_emoji="robot",
        )

    with pytest.raises(ValueError, match="チャンネル"):
        SlackNotificationSettings(
            webhook_url="https://hooks.slack.test/services/1",
            channel="alerts",
        )
