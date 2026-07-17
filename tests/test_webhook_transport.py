"""UrlLibWebhookTransportの入力検証テスト。"""

from __future__ import annotations

import pytest

from app.notifications.webhook_models import (
    WebhookRequest,
)
from app.notifications.webhook_transport import (
    UrlLibWebhookTransport,
)


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
