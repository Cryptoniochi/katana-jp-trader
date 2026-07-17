"""通知ルールに従って選択チャネルへ配信する。"""

from __future__ import annotations

from app.notifications.notification_channels import (
    NotificationChannel,
)
from app.notifications.notification_models import (
    NotificationMessage,
)
from app.notifications.notification_rule_engine import (
    NotificationRuleEngine,
)
from app.notifications.notification_rule_models import (
    RuleBasedNotificationResult,
)
from app.notifications.notification_service import (
    NotificationService,
)


class RuleBasedNotificationService:
    """ルーティング判定後に選択チャネルだけへ通知する。"""

    def __init__(
        self,
        *,
        channels: tuple[NotificationChannel, ...],
        rule_engine: NotificationRuleEngine,
    ) -> None:
        """通知チャネルとルールエンジンを設定する。"""

        channel_map: dict[str, NotificationChannel] = {}

        for channel in channels:
            name = channel.channel_name.strip()

            if not name:
                raise ValueError(
                    "通知チャネル名を指定してください。"
                )

            if name in channel_map:
                raise ValueError(
                    "同じ通知チャネル名が重複しています。 "
                    f"channel={name}"
                )

            channel_map[name] = channel

        self._channels = channel_map
        self.rule_engine = rule_engine

    def deliver(
        self,
        notification: NotificationMessage,
        *,
        continue_on_error: bool = True,
    ) -> RuleBasedNotificationResult:
        """ルール評価後に通知を配信する。"""

        routing = self.rule_engine.evaluate(
            notification,
            available_channel_names=self._channels,
        )

        if not routing.should_deliver:
            return RuleBasedNotificationResult(
                routing=routing,
                delivery=None,
            )

        selected = tuple(
            self._channels[name]
            for name in routing.channel_names
        )
        service = NotificationService(
            channels=selected,
            deduplicate=False,
        )
        delivery = service.deliver(
            notification,
            continue_on_error=continue_on_error,
        )

        return RuleBasedNotificationResult(
            routing=routing,
            delivery=delivery,
        )
