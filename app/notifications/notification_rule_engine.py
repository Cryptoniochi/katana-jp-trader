"""重大度・時間帯・重複・通知回数を評価する。"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Iterable
from datetime import datetime, timezone

from app.notifications.notification_models import (
    NotificationMessage,
    NotificationSeverity,
)
from app.notifications.notification_rule_models import (
    NotificationRoutingResult,
    NotificationRuleDecision,
    NotificationRulePolicy,
    NotificationSuppressionReason,
)


class NotificationRuleEngine:
    """通知先の決定とスパム抑止を行う。"""

    def __init__(
        self,
        *,
        policy: NotificationRulePolicy | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        """通知方針・時計・内部状態を初期化する。"""

        self.policy = policy or NotificationRulePolicy()
        self.now_provider = (
            now_provider
            if now_provider is not None
            else lambda: datetime.now(timezone.utc)
        )
        self._last_delivery_by_signature: dict[
            str,
            datetime,
        ] = {}
        self._delivery_timestamps: deque[datetime] = deque()

    def evaluate(
        self,
        notification: NotificationMessage,
        *,
        available_channel_names: Iterable[str],
    ) -> NotificationRoutingResult:
        """通知を評価し、配信先または抑止理由を返す。"""

        evaluated_at = self._current_time()
        available = frozenset(
            channel.strip()
            for channel in available_channel_names
            if channel.strip()
        )
        configured = self.policy.channels_for(
            notification.severity
        )
        channels = tuple(
            channel
            for channel in configured
            if channel in available
        )

        reasons: list[NotificationSuppressionReason] = []

        if not channels:
            reasons.append(
                NotificationSuppressionReason.NO_CHANNEL
            )

        if (
            notification.severity
            in self.policy.quiet_hours_suppressed_severities
            and self._is_quiet_hours(evaluated_at)
        ):
            reasons.append(
                NotificationSuppressionReason.QUIET_HOURS
            )

        signature = self._signature(notification)

        if self._is_duplicate(
            signature=signature,
            evaluated_at=evaluated_at,
        ):
            reasons.append(
                NotificationSuppressionReason
                .DUPLICATE_COOLDOWN
            )

        self._remove_expired_rate_entries(evaluated_at)

        bypass_rate_limit = (
            notification.severity
            is NotificationSeverity.CRITICAL
            and self.policy.critical_bypasses_rate_limit
        )

        if (
            not bypass_rate_limit
            and len(self._delivery_timestamps)
            >= self.policy.maximum_notifications_per_window
        ):
            reasons.append(
                NotificationSuppressionReason.RATE_LIMIT
            )

        if reasons:
            return NotificationRoutingResult(
                notification=notification,
                decision=NotificationRuleDecision.SUPPRESS,
                channel_names=(),
                reasons=tuple(dict.fromkeys(reasons)),
                evaluated_at=evaluated_at,
            )

        self._last_delivery_by_signature[
            signature
        ] = evaluated_at
        self._delivery_timestamps.append(evaluated_at)

        return NotificationRoutingResult(
            notification=notification,
            decision=NotificationRuleDecision.ROUTE,
            channel_names=channels,
            reasons=(),
            evaluated_at=evaluated_at,
        )

    def reset(self) -> None:
        """重複・流量制御の内部状態を消去する。"""

        self._last_delivery_by_signature.clear()
        self._delivery_timestamps.clear()

    def _is_quiet_hours(
        self,
        current: datetime,
    ) -> bool:
        """現在時刻が静穏時間帯か返す。"""

        start = self.policy.quiet_hours_start_hour
        end = self.policy.quiet_hours_end_hour
        hour = current.hour

        if start == end:
            return False

        if start < end:
            return start <= hour < end

        return hour >= start or hour < end

    def _is_duplicate(
        self,
        *,
        signature: str,
        evaluated_at: datetime,
    ) -> bool:
        """同一内容がCooldown内に配信済みか返す。"""

        if self.policy.duplicate_cooldown_seconds == 0:
            return False

        previous = self._last_delivery_by_signature.get(
            signature
        )

        if previous is None:
            return False

        elapsed = (
            evaluated_at - previous
        ).total_seconds()

        return (
            elapsed
            < self.policy.duplicate_cooldown_seconds
        )

    def _remove_expired_rate_entries(
        self,
        evaluated_at: datetime,
    ) -> None:
        """時間幅外の通知履歴を削除する。"""

        while self._delivery_timestamps:
            elapsed = (
                evaluated_at
                - self._delivery_timestamps[0]
            ).total_seconds()

            if elapsed < self.policy.rate_window_seconds:
                break

            self._delivery_timestamps.popleft()

    @staticmethod
    def _signature(
        notification: NotificationMessage,
    ) -> str:
        """重複判定用の内容署名を返す。"""

        return "|".join(
            (
                notification.severity.value,
                notification.source,
                notification.title,
                notification.body,
            )
        )

    def _current_time(self) -> datetime:
        """UTCへ正規化した現在日時を返す。"""

        current = self.now_provider()

        if current.tzinfo is None:
            raise ValueError(
                "現在日時にはタイムゾーンが必要です。"
            )

        return current.astimezone(timezone.utc)
