"""Webhook共通モデルのテスト。"""

from __future__ import annotations

import pytest

from app.notifications.webhook_models import (
    WebhookAttemptResult,
    WebhookDeliveryResult,
    WebhookRequest,
    WebhookResponse,
    WebhookRetryDecision,
    WebhookRetryPolicy,
)


def test_retry_policy_calculates_capped_backoff() -> None:
    """指数バックオフと上限を適用する。"""

    policy = WebhookRetryPolicy(
        initial_backoff_seconds=1.0,
        backoff_multiplier=2.0,
        maximum_backoff_seconds=3.0,
    )

    assert policy.backoff_seconds(1) == 1.0
    assert policy.backoff_seconds(2) == 2.0
    assert policy.backoff_seconds(3) == 3.0
    assert policy.backoff_seconds(4) == 3.0


def test_retry_policy_rejects_invalid_values() -> None:
    """不正な再試行条件を拒否する。"""

    with pytest.raises(ValueError):
        WebhookRetryPolicy(maximum_attempts=0)

    with pytest.raises(ValueError):
        WebhookRetryPolicy(backoff_multiplier=0.5)

    with pytest.raises(ValueError):
        WebhookRetryPolicy(
            retryable_status_codes=frozenset({700})
        )


def test_request_uses_defensive_copies() -> None:
    """PayloadとHeadersを防御的コピーする。"""

    payload = {"message": "hello"}
    headers = {"X-Test": "1"}

    request = WebhookRequest(
        url=" https://example.test/hook ",
        payload=payload,
        headers=headers,
    )
    payload["message"] = "changed"
    headers["X-Test"] = "2"

    assert request.url == "https://example.test/hook"
    assert request.payload == {"message": "hello"}
    assert request.headers == {"X-Test": "1"}


def test_response_success_property() -> None:
    """2xxだけを成功と判定する。"""

    assert WebhookResponse(204).is_successful
    assert WebhookResponse(299).is_successful
    assert WebhookResponse(300).is_successful is False


def test_delivery_result_reports_success_and_attempt_count() -> None:
    """全体送信結果の便利プロパティを返す。"""

    response = WebhookResponse(200, "ok")
    result = WebhookDeliveryResult(
        url="https://example.test/hook",
        attempts=(
            WebhookAttemptResult(
                attempt_number=1,
                decision=WebhookRetryDecision.SUCCEEDED,
                status_code=200,
                error_message=None,
            ),
        ),
        response=response,
    )

    assert result.succeeded
    assert result.attempt_count == 1
