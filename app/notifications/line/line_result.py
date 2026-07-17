"""LINE Messaging API送信結果モデル。"""

from __future__ import annotations

from dataclasses import dataclass

from app.notifications.webhook_models import (
    WebhookDeliveryResult,
)


@dataclass(frozen=True, slots=True)
class LineDeliveryResult:
    """LINE Push Message送信結果。"""

    destination_id: str
    delivery: WebhookDeliveryResult

    def __post_init__(self) -> None:
        """送信先を検証して正規化する。"""

        destination_id = self.destination_id.strip()

        if not destination_id:
            raise ValueError(
                "LINE送信先IDを指定してください。"
            )

        object.__setattr__(
            self,
            "destination_id",
            destination_id,
        )

    @property
    def succeeded(self) -> bool:
        """LINE送信が成功したか返す。"""

        return self.delivery.succeeded

    @property
    def attempt_count(self) -> int:
        """LINE送信試行回数を返す。"""

        return self.delivery.attempt_count
