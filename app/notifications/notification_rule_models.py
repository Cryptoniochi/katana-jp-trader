"""通知ルール判定の共通モデル。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from app.notifications.notification_models import (
    NotificationDeliveryResult,
    NotificationMessage,
    NotificationSeverity,
)


class NotificationRuleDecision(StrEnum):
    """通知ルールの判定結果。"""

    ROUTE = "route"
    SUPPRESS = "suppress"


class NotificationSuppressionReason(StrEnum):
    """通知を抑止した理由。"""

    QUIET_HOURS = "quiet_hours"
    DUPLICATE_COOLDOWN = "duplicate_cooldown"
    RATE_LIMIT = "rate_limit"
    NO_CHANNEL = "no_channel"


@dataclass(frozen=True, slots=True)
class NotificationRulePolicy:
    """重大度・時間帯・重複・流量制御の方針。"""

    info_channels: tuple[str, ...] = ("file",)
    warning_channels: tuple[str, ...] = (
        "discord",
        "slack",
    )
    error_channels: tuple[str, ...] = (
        "discord",
        "slack",
    )
    critical_channels: tuple[str, ...] = (
        "discord",
        "slack",
    )

    quiet_hours_start_hour: int = 22
    quiet_hours_end_hour: int = 7
    quiet_hours_suppressed_severities: frozenset[
        NotificationSeverity
    ] = field(
        default_factory=lambda: frozenset(
            {NotificationSeverity.INFO}
        )
    )

    duplicate_cooldown_seconds: float = 300.0
    rate_window_seconds: float = 60.0
    maximum_notifications_per_window: int = 20
    critical_bypasses_rate_limit: bool = True

    def __post_init__(self) -> None:
        """ルール設定を検証して正規化する。"""

        for name, value in {
            "静穏時間開始時刻": self.quiet_hours_start_hour,
            "静穏時間終了時刻": self.quiet_hours_end_hour,
        }.items():
            if not 0 <= value <= 23:
                raise ValueError(
                    f"{name}は0以上23以下である必要があります。"
                )

        if self.duplicate_cooldown_seconds < 0:
            raise ValueError(
                "重複通知抑止秒数は0以上である必要があります。"
            )

        if self.rate_window_seconds <= 0:
            raise ValueError(
                "通知回数制限の時間幅は0より大きい必要があります。"
            )

        if self.maximum_notifications_per_window <= 0:
            raise ValueError(
                "時間幅内の最大通知数は0より大きい必要があります。"
            )

        for field_name in (
            "info_channels",
            "warning_channels",
            "error_channels",
            "critical_channels",
        ):
            raw_channels = getattr(self, field_name)
            normalized_channels = tuple(
                dict.fromkeys(
                    channel.strip()
                    for channel in raw_channels
                    if channel.strip()
                )
            )
            object.__setattr__(
                self,
                field_name,
                normalized_channels,
            )

        object.__setattr__(
            self,
            "quiet_hours_suppressed_severities",
            frozenset(
                NotificationSeverity(severity)
                for severity in (
                    self.quiet_hours_suppressed_severities
                )
            ),
        )

    def channels_for(
        self,
        severity: NotificationSeverity,
    ) -> tuple[str, ...]:
        """重大度に対応する通知先名を返す。"""

        mapping = {
            NotificationSeverity.INFO: self.info_channels,
            NotificationSeverity.WARNING: (
                self.warning_channels
            ),
            NotificationSeverity.ERROR: self.error_channels,
            NotificationSeverity.CRITICAL: (
                self.critical_channels
            ),
        }
        return mapping[severity]


@dataclass(frozen=True, slots=True)
class NotificationRoutingResult:
    """1通知のルーティング判定結果。"""

    notification: NotificationMessage
    decision: NotificationRuleDecision
    channel_names: tuple[str, ...]
    reasons: tuple[NotificationSuppressionReason, ...]
    evaluated_at: datetime

    def __post_init__(self) -> None:
        """判定結果の整合性を検証する。"""

        if self.evaluated_at.tzinfo is None:
            raise ValueError(
                "ルール評価日時にはタイムゾーンが必要です。"
            )

        if (
            self.decision is NotificationRuleDecision.ROUTE
            and not self.channel_names
        ):
            raise ValueError(
                "配信判定には1件以上の通知先が必要です。"
            )

        if (
            self.decision
            is NotificationRuleDecision.SUPPRESS
            and not self.reasons
        ):
            raise ValueError(
                "抑止判定には1件以上の理由が必要です。"
            )

        if (
            self.decision is NotificationRuleDecision.ROUTE
            and self.reasons
        ):
            raise ValueError(
                "配信判定には抑止理由を設定できません。"
            )

    @property
    def should_deliver(self) -> bool:
        """通知を配信すべきか返す。"""

        return self.decision is NotificationRuleDecision.ROUTE


@dataclass(frozen=True, slots=True)
class RuleBasedNotificationResult:
    """ルール判定と実配信をまとめた結果。"""

    routing: NotificationRoutingResult
    delivery: NotificationDeliveryResult | None

    def __post_init__(self) -> None:
        """ルール判定と配信結果の整合性を検証する。"""

        if self.routing.should_deliver and self.delivery is None:
            raise ValueError(
                "配信判定には通知配信結果が必要です。"
            )

        if (
            not self.routing.should_deliver
            and self.delivery is not None
        ):
            raise ValueError(
                "抑止判定には通知配信結果を設定できません。"
            )
