"""LINE Messaging API応答の補助モデル。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from app.notifications.webhook_models import (
    WebhookDeliveryResult,
)


@dataclass(frozen=True, slots=True)
class LineApiError:
    """LINE Messaging APIエラー情報。"""

    message: str
    details: tuple[dict[str, Any], ...] = ()

    def __post_init__(self) -> None:
        """エラー内容を検証して防御的コピーする。"""

        message = self.message.strip()

        if not message:
            raise ValueError(
                "LINE APIエラーメッセージを指定してください。"
            )

        object.__setattr__(self, "message", message)
        object.__setattr__(
            self,
            "details",
            tuple(dict(item) for item in self.details),
        )


def parse_line_api_error(
    delivery: WebhookDeliveryResult,
) -> LineApiError | None:
    """失敗応答BodyからLINE APIエラーを解析する。"""

    response = delivery.response

    if response is None or response.is_successful:
        return None

    body = response.body.strip()

    if not body:
        return LineApiError(
            message=(
                "LINE Messaging APIが失敗応答を返しました。 "
                f"status_code={response.status_code}"
            )
        )

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return LineApiError(message=body)

    if not isinstance(payload, dict):
        return LineApiError(message=body)

    message = str(
        payload.get(
            "message",
            (
                "LINE Messaging APIが失敗応答を返しました。 "
                f"status_code={response.status_code}"
            ),
        )
    )
    raw_details = payload.get("details", [])

    details = (
        tuple(
            dict(item)
            for item in raw_details
            if isinstance(item, dict)
        )
        if isinstance(raw_details, list)
        else ()
    )

    return LineApiError(
        message=message,
        details=details,
    )
