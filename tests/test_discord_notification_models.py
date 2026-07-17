"""DiscordNotificationSettingsのテスト。"""

import pytest

from app.notifications.discord_notification_models import (
    DiscordNotificationSettings,
)


def test_settings_normalizes_values() -> None:
    settings = DiscordNotificationSettings(
        webhook_url=" https://discord.test/hook ",
        username=" KATANA ",
        avatar_url=" https://example.test/avatar.png ",
        mention=" @here ",
    )

    assert settings.webhook_url == (
        "https://discord.test/hook"
    )
    assert settings.username == "KATANA"
    assert settings.avatar_url == (
        "https://example.test/avatar.png"
    )
    assert settings.mention == "@here"


def test_settings_rejects_invalid_values() -> None:
    with pytest.raises(ValueError, match="Webhook URL"):
        DiscordNotificationSettings(
            webhook_url=" ",
        )

    with pytest.raises(ValueError, match="http"):
        DiscordNotificationSettings(
            webhook_url="discord.test/hook",
        )

    with pytest.raises(ValueError, match="表示名"):
        DiscordNotificationSettings(
            webhook_url="https://discord.test/hook",
            username=" ",
        )
