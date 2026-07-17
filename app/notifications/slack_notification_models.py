"""Slack Incoming Webhook通知の設定モデル。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SlackNotificationSettings:
    """Slack通知チャネルの設定。"""

    webhook_url: str
    username: str = "Project KATANA"
    icon_emoji: str | None = ":crossed_swords:"
    channel: str | None = None
    mention: str | None = None

    def __post_init__(self) -> None:
        """設定値を検証して正規化する。"""

        webhook_url = self.webhook_url.strip()
        username = self.username.strip()
        icon_emoji = (
            None
            if self.icon_emoji is None
            else self.icon_emoji.strip()
        )
        channel = (
            None
            if self.channel is None
            else self.channel.strip()
        )
        mention = (
            None
            if self.mention is None
            else self.mention.strip()
        )

        if not webhook_url:
            raise ValueError(
                "Slack Webhook URLを指定してください。"
            )

        if not webhook_url.startswith(
            ("https://", "http://")
        ):
            raise ValueError(
                "Slack Webhook URLはhttpまたはhttpsで"
                "指定してください。"
            )

        if not username:
            raise ValueError(
                "Slack表示名を指定してください。"
            )

        if len(username) > 80:
            raise ValueError(
                "Slack表示名は80文字以内で指定してください。"
            )

        if icon_emoji is not None and not (
            icon_emoji.startswith(":")
            and icon_emoji.endswith(":")
        ):
            raise ValueError(
                "Slack絵文字は:emoji:形式で指定してください。"
            )

        if channel is not None and not channel.startswith(
            ("#", "@")
        ):
            raise ValueError(
                "Slackチャンネルは#または@で始めてください。"
            )

        object.__setattr__(
            self,
            "webhook_url",
            webhook_url,
        )
        object.__setattr__(
            self,
            "username",
            username,
        )
        object.__setattr__(
            self,
            "icon_emoji",
            icon_emoji or None,
        )
        object.__setattr__(
            self,
            "channel",
            channel or None,
        )
        object.__setattr__(
            self,
            "mention",
            mention or None,
        )
