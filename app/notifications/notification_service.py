"""通知メッセージを複数チャネルへ配信する。"""

from __future__ import annotations

from app.notifications.notification_channels import (
    NotificationChannel,
)
from app.notifications.notification_models import (
    NotificationChannelResult,
    NotificationDeliveryDecision,
    NotificationDeliveryResult,
    NotificationMessage,
)


class NotificationService:
    """通知の重複防止と複数チャネル配信を管理する。"""

    def __init__(
        self,
        *,
        channels: tuple[NotificationChannel, ...],
        deduplicate: bool = True,
    ) -> None:
        self.channels = channels
        self.deduplicate = deduplicate
        self._delivered_ids: set[str] = set()

    def deliver(
        self,
        notification: NotificationMessage,
        *,
        continue_on_error: bool = True,
    ) -> NotificationDeliveryResult:
        """通知を全チャネルへ配信する。"""

        if (
            self.deduplicate
            and notification.notification_id
            in self._delivered_ids
        ):
            return NotificationDeliveryResult(
                notification=notification,
                decision=NotificationDeliveryDecision.SKIPPED,
                channels=(),
            )

        results: list[NotificationChannelResult] = []

        for channel in self.channels:
            try:
                channel.send(notification)
                results.append(
                    NotificationChannelResult(
                        channel_name=channel.channel_name,
                        delivered=True,
                    )
                )
            except Exception as error:
                results.append(
                    NotificationChannelResult(
                        channel_name=channel.channel_name,
                        delivered=False,
                        error_message=(
                            str(error).strip()
                            or type(error).__name__
                        ),
                    )
                )
                if not continue_on_error:
                    raise

        delivered_count = sum(
            result.delivered
            for result in results
        )

        if not results:
            decision = NotificationDeliveryDecision.SKIPPED
        elif delivered_count == len(results):
            decision = NotificationDeliveryDecision.COMPLETED
        elif delivered_count > 0:
            decision = (
                NotificationDeliveryDecision
                .COMPLETED_WITH_ERRORS
            )
        else:
            decision = NotificationDeliveryDecision.FAILED

        if delivered_count > 0 and self.deduplicate:
            self._delivered_ids.add(
                notification.notification_id
            )

        return NotificationDeliveryResult(
            notification=notification,
            decision=decision,
            channels=tuple(results),
        )

    def clear_deduplication(self) -> None:
        """重複通知履歴を消去する。"""

        self._delivered_ids.clear()
