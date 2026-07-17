"""通知チャネルの共通実装。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

from app.notifications.notification_models import (
    NotificationMessage,
)


class NotificationChannel(Protocol):
    """通知先チャネルの共通インターフェース。"""

    @property
    def channel_name(self) -> str:
        """チャネル名を返す。"""

    def send(self, message: NotificationMessage) -> None:
        """通知を送信する。"""


class ConsoleNotificationChannel:
    """標準出力へ通知する。"""

    @property
    def channel_name(self) -> str:
        return "console"

    def send(self, message: NotificationMessage) -> None:
        print(
            f"[{message.severity.value.upper()}] "
            f"{message.title}: {message.body}"
        )


class FileNotificationChannel:
    """JSON Lines形式で通知を保存する。"""

    def __init__(self, *, path: Path) -> None:
        self.path = path

    @property
    def channel_name(self) -> str:
        return "file"

    def send(self, message: NotificationMessage) -> None:
        self.path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        payload = {
            "notification_id": message.notification_id,
            "title": message.title,
            "body": message.body,
            "severity": message.severity.value,
            "created_at": message.created_at.isoformat(),
            "source": message.source,
            "metadata": message.metadata,
        }

        with self.path.open(
            "a",
            encoding="utf-8",
            newline="\n",
        ) as file:
            file.write(
                json.dumps(
                    payload,
                    ensure_ascii=False,
                    sort_keys=True,
                )
                + "\n"
            )
