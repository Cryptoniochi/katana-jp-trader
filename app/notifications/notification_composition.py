"""外部通知チャネルとNotification Gatewayを組み立てる。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from app.notifications.discord_notification_channel import (
    DiscordNotificationChannel,
)
from app.notifications.discord_notification_models import (
    DiscordNotificationSettings,
)
from app.notifications.line.line_client import (
    LineMessagingClient,
)
from app.notifications.line.line_models import (
    LineNotificationSettings,
)
from app.notifications.line.line_notification_channel import (
    LineNotificationChannel,
)
from app.notifications.line.line_notification_service import (
    LineNotificationService,
)
from app.notifications.line.line_sender import (
    LineMessagingSender,
)
from app.notifications.notification_channels import (
    NotificationChannel,
)
from app.notifications.notification_gateway import (
    NotificationGateway,
)
from app.notifications.notification_rule_engine import (
    NotificationRuleEngine,
)
from app.notifications.notification_rule_models import (
    NotificationRulePolicy,
)
from app.notifications.notification_rule_service import (
    RuleBasedNotificationService,
)
from app.settings import NotificationSettings


NowProvider = Callable[[], datetime]


class NotificationConfigurationError(ValueError):
    """利用可能な外部通知チャネルがないことを表す。"""


@dataclass(frozen=True, slots=True)
class NotificationCompositionBundle:
    """通知Compositionが生成した主要Component。"""

    settings: NotificationSettings
    gateway: NotificationGateway
    sender: RuleBasedNotificationService
    rule_engine: NotificationRuleEngine
    channels: tuple[NotificationChannel, ...]

    @property
    def channel_names(self) -> tuple[str, ...]:
        """有効な通知チャネル名を返す。"""

        return tuple(
            channel.channel_name
            for channel in self.channels
        )


class NotificationComposition:
    """設定値から外部通知機能を組み立てる。"""

    @staticmethod
    def create(
        *,
        settings: NotificationSettings,
        policy: NotificationRulePolicy | None = None,
        now_provider: NowProvider | None = None,
        require_channel: bool = True,
    ) -> NotificationCompositionBundle:
        """設定済みのDiscord・LINEチャネルを生成する。"""

        channels: list[NotificationChannel] = []

        if settings.discord_enabled:
            webhook_url = settings.discord_webhook_url
            assert webhook_url is not None

            channels.append(
                DiscordNotificationChannel(
                    settings=DiscordNotificationSettings(
                        webhook_url=webhook_url,
                        username="Project KATANA",
                    )
                )
            )

        if settings.line_enabled:
            channel_access_token = (
                settings.line_channel_access_token
            )
            destination_id = settings.line_destination_id
            assert channel_access_token is not None
            assert destination_id is not None

            line_settings = LineNotificationSettings(
                channel_access_token=channel_access_token,
                destination_id=destination_id,
            )
            line_client = LineMessagingClient(
                settings=line_settings
            )
            line_sender = LineMessagingSender(
                client=line_client
            )
            line_service = LineNotificationService(
                sender=line_sender
            )
            channels.append(
                LineNotificationChannel(
                    settings=line_settings,
                    service=line_service,
                )
            )

        resolved_channels = tuple(channels)

        if require_channel and not resolved_channels:
            raise NotificationConfigurationError(
                "通知チャネルが設定されていません。"
                " .envに"
                " KATANA_DISCORD_WEBHOOK_URL"
                " または"
                " KATANA_LINE_CHANNEL_ACCESS_TOKENと"
                " KATANA_LINE_DESTINATION_IDを設定してください。"
            )

        rule_engine = NotificationRuleEngine(
            policy=policy,
            now_provider=now_provider,
        )
        sender = RuleBasedNotificationService(
            channels=resolved_channels,
            rule_engine=rule_engine,
        )
        gateway = NotificationGateway(
            sender=sender
        )

        return NotificationCompositionBundle(
            settings=settings,
            gateway=gateway,
            sender=sender,
            rule_engine=rule_engine,
            channels=resolved_channels,
        )
