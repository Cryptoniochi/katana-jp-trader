"""NotificationCompositionのテスト。"""

from datetime import datetime, timezone

import pytest

from app.notifications.notification_composition import (
    NotificationComposition,
    NotificationConfigurationError,
)
from app.settings import NotificationSettings


NOW = datetime(
    2026,
    7,
    19,
    0,
    0,
    tzinfo=timezone.utc,
)


def test_create_builds_discord_and_line_channels() -> None:
    bundle = NotificationComposition.create(
        settings=NotificationSettings(
            discord_webhook_url=(
                "https://discord.test/webhook"
            ),
            line_channel_access_token="secret-token",
            line_destination_id="U1234567890",
        ),
        now_provider=lambda: NOW,
    )

    assert bundle.channel_names == (
        "discord",
        "line",
    )
    assert bundle.gateway.sender is bundle.sender
    assert bundle.sender.rule_engine is bundle.rule_engine


def test_create_builds_only_configured_channel() -> None:
    bundle = NotificationComposition.create(
        settings=NotificationSettings(
            discord_webhook_url=(
                "https://discord.test/webhook"
            ),
        ),
    )

    assert bundle.channel_names == ("discord",)


def test_create_rejects_empty_configuration() -> None:
    with pytest.raises(
        NotificationConfigurationError,
        match="通知チャネル",
    ):
        NotificationComposition.create(
            settings=NotificationSettings()
        )


def test_create_can_allow_empty_configuration() -> None:
    bundle = NotificationComposition.create(
        settings=NotificationSettings(),
        require_channel=False,
    )

    assert bundle.channel_names == ()
