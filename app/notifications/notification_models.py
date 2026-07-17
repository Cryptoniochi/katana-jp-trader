"""通知メッセージと配信結果の共通モデル。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class NotificationSeverity(StrEnum):
    """通知の重大度。"""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass(frozen=True, slots=True)
class NotificationMessage:
    """通知チャネルへ送る共通メッセージ。"""

    notification_id: str
    title: str
    body: str
    severity: NotificationSeverity
    created_at: datetime
    source: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """通知内容を検証して正規化する。"""

        notification_id = self.notification_id.strip()
        title = self.title.strip()
        body = self.body.strip()
        source = self.source.strip()

        if not notification_id:
            raise ValueError("通知IDを指定してください。")
        if not title:
            raise ValueError("通知タイトルを指定してください。")
        if not body:
            raise ValueError("通知本文を指定してください。")
        if not source:
            raise ValueError("通知発生元を指定してください。")
        if self.created_at.tzinfo is None:
            raise ValueError(
                "通知作成日時にはタイムゾーンが必要です。"
            )
        if not isinstance(self.metadata, dict):
            raise TypeError(
                "通知メタデータは辞書形式で指定してください。"
            )

        object.__setattr__(self, "notification_id", notification_id)
        object.__setattr__(self, "title", title)
        object.__setattr__(self, "body", body)
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "metadata", dict(self.metadata))


class NotificationDeliveryDecision(StrEnum):
    """通知配信結果。"""

    COMPLETED = "completed"
    COMPLETED_WITH_ERRORS = "completed_with_errors"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class NotificationChannelResult:
    """1チャネルへの通知結果。"""

    channel_name: str
    delivered: bool
    error_message: str | None = None

    def __post_init__(self) -> None:
        """配信結果を検証する。"""

        channel_name = self.channel_name.strip()
        error_message = (
            None
            if self.error_message is None
            else self.error_message.strip()
        )

        if not channel_name:
            raise ValueError("通知チャネル名を指定してください。")
        if self.delivered and error_message:
            raise ValueError(
                "配信成功結果にはエラーを設定できません。"
            )
        if not self.delivered and not error_message:
            raise ValueError(
                "配信失敗結果にはエラーが必要です。"
            )

        object.__setattr__(self, "channel_name", channel_name)
        object.__setattr__(
            self,
            "error_message",
            error_message or None,
        )


@dataclass(frozen=True, slots=True)
class NotificationDeliveryResult:
    """複数チャネルへの通知結果。"""

    notification: NotificationMessage
    decision: NotificationDeliveryDecision
    channels: tuple[NotificationChannelResult, ...]

    @property
    def delivered_count(self) -> int:
        """成功チャネル数を返す。"""

        return sum(item.delivered for item in self.channels)

    @property
    def failed_count(self) -> int:
        """失敗チャネル数を返す。"""

        return sum(not item.delivered for item in self.channels)
