"""UrlLibWebhookTransportのテスト。"""

from __future__ import annotations

import json

import pytest

from app.notifications.webhook_models import (
    WebhookRequest,
)
from app.notifications.webhook_transport import (
    DEFAULT_USER_AGENT,
    UrlLibWebhookTransport,
)


class FakeHttpResponse:
    """urlopenが返す最小HTTP応答。"""

    def __init__(
        self,
        *,
        status: int = 204,
        body: bytes = b"",
    ) -> None:
        self.status = status
        self._body = body

    def __enter__(self):
        return self

    def __exit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ) -> None:
        return None

    def read(self) -> bytes:
        return self._body


def test_transport_rejects_non_positive_timeout() -> None:
    """不正なタイムアウトをHTTP通信前に拒否する。"""

    transport = UrlLibWebhookTransport()
    request = WebhookRequest(
        url="https://example.test/hook",
        payload={},
        headers={},
    )

    with pytest.raises(
        ValueError,
        match="タイムアウト",
    ):
        transport.post_json(
            request,
            timeout_seconds=0,
        )


def test_transport_adds_default_json_headers(
    monkeypatch,
) -> None:
    """Discord互換の既定HTTPヘッダーを付与する。"""

    captured = {}

    def fake_urlopen(
        request,
        *,
        timeout,
    ):
        captured["request"] = request
        captured["timeout"] = timeout

        return FakeHttpResponse(
            status=204
        )

    monkeypatch.setattr(
        "app.notifications.webhook_transport.urlopen",
        fake_urlopen,
    )

    transport = UrlLibWebhookTransport()
    result = transport.post_json(
        WebhookRequest(
            url="https://discord.test/webhook",
            payload={
                "content": "Project KATANA",
            },
            headers={},
        ),
        timeout_seconds=12.5,
    )

    http_request = captured["request"]

    assert result.status_code == 204
    assert captured["timeout"] == 12.5
    assert http_request.get_method() == "POST"
    assert http_request.get_header(
        "Content-type"
    ) == "application/json"
    assert http_request.get_header(
        "Accept"
    ) == "application/json"
    assert http_request.get_header(
        "User-agent"
    ) == DEFAULT_USER_AGENT
    assert json.loads(
        http_request.data.decode("utf-8")
    ) == {
        "content": "Project KATANA",
    }


def test_request_headers_override_transport_defaults(
    monkeypatch,
) -> None:
    """チャネル固有ヘッダーは既定値より優先される。"""

    captured = {}

    def fake_urlopen(
        request,
        *,
        timeout,
    ):
        captured["request"] = request

        return FakeHttpResponse(
            status=200,
            body=b"{}",
        )

    monkeypatch.setattr(
        "app.notifications.webhook_transport.urlopen",
        fake_urlopen,
    )

    transport = UrlLibWebhookTransport()
    result = transport.post_json(
        WebhookRequest(
            url="https://api.example.test/messages",
            payload={
                "message": "test",
            },
            headers={
                "Authorization": "Bearer test-token",
                "User-Agent": "Custom-Client/1.0",
            },
        ),
        timeout_seconds=10,
    )

    http_request = captured["request"]

    assert result.status_code == 200
    assert result.body == "{}"
    assert http_request.get_header(
        "Authorization"
    ) == "Bearer test-token"
    assert http_request.get_header(
        "User-agent"
    ) == "Custom-Client/1.0"
