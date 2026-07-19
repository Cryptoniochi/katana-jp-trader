"""Webhook HTTP送信処理。"""

from __future__ import annotations

import json
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.notifications.webhook_models import (
    WebhookRequest,
    WebhookResponse,
)


DEFAULT_USER_AGENT = "Project-KATANA/0.9"


class WebhookTransportError(RuntimeError):
    """Webhook通信自体に失敗したことを表す。"""


class WebhookTransport(Protocol):
    """Webhook HTTP通信の共通インターフェース。"""

    def post_json(
        self,
        request: WebhookRequest,
        *,
        timeout_seconds: float,
    ) -> WebhookResponse:
        """JSONをPOSTして応答を返す。"""


class UrlLibWebhookTransport:
    """Python標準ライブラリを使うWebhook Transport。"""

    def post_json(
        self,
        request: WebhookRequest,
        *,
        timeout_seconds: float,
    ) -> WebhookResponse:
        """JSON PayloadをHTTP POSTする。"""

        if timeout_seconds <= 0:
            raise ValueError(
                "タイムアウト秒数は0より大きい必要があります。"
            )

        body = json.dumps(
            request.payload,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": DEFAULT_USER_AGENT,
            **request.headers,
        }

        http_request = Request(
            request.url,
            data=body,
            headers=headers,
            method="POST",
        )

        try:
            with urlopen(
                http_request,
                timeout=timeout_seconds,
            ) as response:
                response_body = response.read().decode(
                    "utf-8",
                    errors="replace",
                )

                return WebhookResponse(
                    status_code=int(response.status),
                    body=response_body,
                )

        except HTTPError as error:
            response_body = error.read().decode(
                "utf-8",
                errors="replace",
            )

            return WebhookResponse(
                status_code=int(error.code),
                body=response_body,
            )

        except (URLError, TimeoutError, OSError) as error:
            raise WebhookTransportError(
                "Webhook通信に失敗しました。 "
                f"url={request.url} "
                f"error={error}"
            ) from error
