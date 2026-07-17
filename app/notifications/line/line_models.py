"""LINE Messaging API通知の共通モデル。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class LineDestinationType(StrEnum):
    """LINE Push Messageの宛先種別。"""

    USER = "user"
    GROUP = "group"
    ROOM = "room"


@dataclass(frozen=True, slots=True)
class LineNotificationSettings:
    """LINE Messaging API接続設定。"""

    channel_access_token: str
    destination_id: str
    destination_type: LineDestinationType = (
        LineDestinationType.USER
    )
    api_base_url: str = "https://api.line.me"
    timeout_seconds: float = 10.0
    maximum_attempts: int = 3

    def __post_init__(self) -> None:
        """設定値を検証して正規化する。"""

        token = self.channel_access_token.strip()
        destination_id = self.destination_id.strip()
        api_base_url = self.api_base_url.strip().rstrip("/")

        if not token:
            raise ValueError(
                "LINE Channel Access Tokenを指定してください。"
            )

        if not destination_id:
            raise ValueError(
                "LINE送信先IDを指定してください。"
            )

        expected_prefix = {
            LineDestinationType.USER: "U",
            LineDestinationType.GROUP: "C",
            LineDestinationType.ROOM: "R",
        }[self.destination_type]

        if not destination_id.startswith(expected_prefix):
            raise ValueError(
                "LINE送信先IDの形式が宛先種別と一致しません。 "
                f"destination_type={self.destination_type.value}"
            )

        if not api_base_url.startswith(
            ("https://", "http://")
        ):
            raise ValueError(
                "LINE API Base URLはhttpまたはhttpsで"
                "指定してください。"
            )

        if self.timeout_seconds <= 0:
            raise ValueError(
                "LINE API Timeoutは0より大きい必要があります。"
            )

        if self.maximum_attempts <= 0:
            raise ValueError(
                "LINE API最大試行回数は0より大きい必要があります。"
            )

        object.__setattr__(
            self,
            "channel_access_token",
            token,
        )
        object.__setattr__(
            self,
            "destination_id",
            destination_id,
        )
        object.__setattr__(
            self,
            "api_base_url",
            api_base_url,
        )

    @property
    def push_message_url(self) -> str:
        """Push Message APIのURLを返す。"""

        return (
            f"{self.api_base_url}"
            "/v2/bot/message/push"
        )

    def masked_summary(self) -> dict[str, object]:
        """秘密値を隠した設定サマリーを返す。"""

        return {
            "channel_access_token": _mask_secret(
                self.channel_access_token
            ),
            "destination_id": _mask_secret(
                self.destination_id
            ),
            "destination_type": self.destination_type.value,
            "api_base_url": self.api_base_url,
            "timeout_seconds": self.timeout_seconds,
            "maximum_attempts": self.maximum_attempts,
        }


@dataclass(frozen=True, slots=True)
class LineTextMessage:
    """LINEへ送るText Message。"""

    text: str

    def __post_init__(self) -> None:
        """本文を検証して正規化する。"""

        text = self.text.strip()

        if not text:
            raise ValueError(
                "LINE通知本文を指定してください。"
            )

        if len(text) > 5000:
            raise ValueError(
                "LINE通知本文は5000文字以内で指定してください。"
            )

        object.__setattr__(self, "text", text)

    def to_payload(self) -> dict[str, str]:
        """LINE API用Message Objectを返す。"""

        return {
            "type": "text",
            "text": self.text,
        }


@dataclass(frozen=True, slots=True)
class LinePushMessageRequest:
    """LINE Push Message APIへの送信要求。"""

    destination_id: str
    messages: tuple[LineTextMessage, ...]

    def __post_init__(self) -> None:
        """宛先とMessage数を検証する。"""

        destination_id = self.destination_id.strip()

        if not destination_id:
            raise ValueError(
                "LINE送信先IDを指定してください。"
            )

        if not self.messages:
            raise ValueError(
                "LINE通知には1件以上のMessageが必要です。"
            )

        if len(self.messages) > 5:
            raise ValueError(
                "LINE通知は1回の要求につき5件までです。"
            )

        object.__setattr__(
            self,
            "destination_id",
            destination_id,
        )

    def to_payload(self) -> dict[str, object]:
        """LINE Push Message API用Payloadを返す。"""

        return {
            "to": self.destination_id,
            "messages": [
                message.to_payload()
                for message in self.messages
            ],
        }


def _mask_secret(
    value: str,
) -> str:
    """秘密値を安全な表示へ変換する。"""

    if len(value) <= 4:
        return "*" * len(value)

    return (
        value[:2]
        + "*" * (len(value) - 4)
        + value[-2:]
    )
