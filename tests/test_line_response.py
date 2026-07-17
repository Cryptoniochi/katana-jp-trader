"""LINE APIエラー解析のテスト。"""

from app.notifications.line.line_response import (
    parse_line_api_error,
)
from app.notifications.webhook_models import (
    WebhookAttemptResult,
    WebhookDeliveryResult,
    WebhookResponse,
    WebhookRetryDecision,
)


def delivery(
    *,
    status_code: int,
    body: str,
) -> WebhookDeliveryResult:
    return WebhookDeliveryResult(
        url="https://api.line.me/v2/bot/message/push",
        attempts=(
            WebhookAttemptResult(
                attempt_number=1,
                decision=(
                    WebhookRetryDecision.FAILED
                    if status_code >= 300
                    else WebhookRetryDecision.SUCCEEDED
                ),
                status_code=status_code,
                error_message=(
                    "failed"
                    if status_code >= 300
                    else None
                ),
            ),
        ),
        response=WebhookResponse(
            status_code=status_code,
            body=body,
        ),
    )


def test_parser_returns_none_for_success() -> None:
    assert parse_line_api_error(
        delivery(
            status_code=200,
            body="{}",
        )
    ) is None


def test_parser_reads_json_error() -> None:
    error = parse_line_api_error(
        delivery(
            status_code=400,
            body=(
                '{"message":"invalid request",'
                '"details":[{"message":"invalid to"}]}'
            ),
        )
    )

    assert error is not None
    assert error.message == "invalid request"
    assert error.details == (
        {"message": "invalid to"},
    )


def test_parser_handles_non_json_body() -> None:
    error = parse_line_api_error(
        delivery(
            status_code=500,
            body="server error",
        )
    )

    assert error is not None
    assert error.message == "server error"
