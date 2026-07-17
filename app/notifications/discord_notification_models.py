"""Discord Webhook通知の設定モデル。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DiscordNotificationSettings:
    """Discord通知チャネルの設定。"""

    webhook_url: str
    username: str = "Project KATANA"
    avatar_url: str | None = None
    mention: str | None = None

    def __post_init__(self) -> None:
        webhook_url = self.webhook_url.strip()
        username = self.username.strip()
        avatar_url = (
            None
            if self.avatar_url is None
            else self.avatar_url.strip()
        )
        mention = (
            None
            if self.mention is None
            else self.mention.strip()
        )

        if not webhook_url:
            raise ValueError(
                "Discord Webhook URLを指定してください。"
            )

        if not webhook_url.startswith(
            ("https://", "http://")
        ):
            raise ValueError(
                "Discord Webhook URLはhttpまたはhttpsで"
                "指定してください。"
            )

        if not username:
            raise ValueError(
                "Discord表示名を指定してください。"
            )

        if len(username) > 80:
            raise ValueError(
                "Discord表示名は80文字以内で指定してください。"
            )

        if avatar_url is not None and not avatar_url.startswith(
            ("https://", "http://")
        ):
            raise ValueError(
                "Discord Avatar URLはhttpまたはhttpsで"
                "指定してください。"
            )

        object.__setattr__(self, "webhook_url", webhook_url)
        object.__setattr__(self, "username", username)
        object.__setattr__(self, "avatar_url", avatar_url or None)
        object.__setattr__(self, "mention", mention or None)
