"""WebhookClientのテスト。"""

from __future__ import annotations

import pytest

from app.notifications.webhook_client import (
    WebhookClient,
    WebhookDeliveryError,
)
from app.notifications.webhook_models import (
    WebhookRequest,
    WebhookResponse,
    WebhookRetryDecision,
    WebhookRetryPolicy,
)


class FakeTransport:
    """順番に応答または例外を返すTransport。"""

    def __init__(self, outcomes) -> None:
        self.outcomes = list(outcomes)
        self.calls = []

    def post_json(
        self,
        request,
        *,
        timeout_seconds: float,
    ):
        self.calls.append(
            (request, timeout_seconds)
        )
        outcome = self.outcomes.pop(0)

        if isinstance(outcome, Exception):
            raise outcome

        return outcome


def request() -> WebhookRequest:
    """テスト用Webhook Requestを返す。"""

    return WebhookRequest(
        url="https://example.test/hook",
        payload={"message": "hello"},
        headers={},
    )


def policy(
    *,
    maximum_attempts: int = 3,
) -> WebhookRetryPolicy:
    """高速テスト用再試行条件を返す。"""

    return WebhookRetryPolicy(
        maximum_attempts=maximum_attempts,
        initial_backoff_seconds=1.0,
        backoff_multiplier=2.0,
        maximum_backoff_seconds=10.0,
        timeout_seconds=5.0,
    )


def test_send_succeeds_on_first_attempt() -> None:
    """初回成功時は再試行しない。"""

    transport = FakeTransport(
        [WebhookResponse(204)]
    )
    sleeps = []
    client = WebhookClient(
        transport=transport,
        policy=policy(),
        sleeper=sleeps.append,
    )

    result = client.send(request())

    assert result.succeeded
    assert result.attempt_count == 1
    assert sleeps == []
    assert transport.calls[0][1] == 5.0


def test_send_retries_retryable_status_then_succeeds() -> None:
    """503応答後に指数バックオフして成功する。"""

    transport = FakeTransport(
        [
            WebhookResponse(503),
            WebhookResponse(429),
            WebhookResponse(200),
        ]
    )
    sleeps = []
    client = WebhookClient(
        transport=transport,
        policy=policy(),
        sleeper=sleeps.append,
    )

    result = client.send(request())

    assert result.succeeded
    assert result.attempt_count == 3
    assert sleeps == [1.0, 2.0]
    assert result.attempts[0].decision is (
        WebhookRetryDecision.RETRYING
    )


def test_send_does_not_retry_non_retryable_status() -> None:
    """400応答は即時失敗とする。"""

    transport = FakeTransport(
        [WebhookResponse(400)]
    )
    client = WebhookClient(
        transport=transport,
        policy=policy(),
        sleeper=lambda _seconds: None,
    )

    result = client.send(
        request(),
        raise_on_failure=False,
    )

    assert result.succeeded is False
    assert result.attempt_count == 1
    assert result.attempts[0].decision is (
        WebhookRetryDecision.FAILED
    )


def test_send_retries_transport_error() -> None:
    """通信例外後も残り試行回数まで再試行する。"""

    transport = FakeTransport(
        [
            RuntimeError("network down"),
            WebhookResponse(200),
        ]
    )
    sleeps = []
    client = WebhookClient(
        transport=transport,
        policy=policy(),
        sleeper=sleeps.append,
    )

    result = client.send(request())

    assert result.succeeded
    assert result.attempt_count == 2
    assert sleeps == [1.0]


def test_send_raises_delivery_error_after_exhaustion() -> None:
    """全試行失敗時は結果付き例外を送出する。"""

    transport = FakeTransport(
        [
            WebhookResponse(503),
            WebhookResponse(503),
        ]
    )
    client = WebhookClient(
        transport=transport,
        policy=policy(maximum_attempts=2),
        sleeper=lambda _seconds: None,
    )

    with pytest.raises(WebhookDeliveryError) as raised:
        client.send(request())

    assert raised.value.result.attempt_count == 2
    assert raised.value.result.succeeded is False


def test_send_can_return_failure_without_raising() -> None:
    """非送出モードでは失敗結果を返す。"""

    transport = FakeTransport(
        [RuntimeError("offline")]
    )
    client = WebhookClient(
        transport=transport,
        policy=policy(maximum_attempts=1),
        sleeper=lambda _seconds: None,
    )

    result = client.send(
        request(),
        raise_on_failure=False,
    )

    assert result.succeeded is False
    assert result.attempts[0].error_message == "offline"
