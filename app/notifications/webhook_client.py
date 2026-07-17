"""タイムアウト・再試行・指数バックオフ付きWebhook Client。"""

from __future__ import annotations

from collections.abc import Callable
from time import sleep

from app.notifications.webhook_models import (
    WebhookAttemptResult,
    WebhookDeliveryResult,
    WebhookRequest,
    WebhookResponse,
    WebhookRetryDecision,
    WebhookRetryPolicy,
)
from app.notifications.webhook_transport import (
    UrlLibWebhookTransport,
    WebhookTransport,
)


class WebhookDeliveryError(RuntimeError):
    """Webhookの全試行が失敗したことを表す。"""

    def __init__(
        self,
        result: WebhookDeliveryResult,
    ) -> None:
        self.result = result

        last_attempt = result.attempts[-1]

        super().__init__(
            "Webhook送信に失敗しました。 "
            f"url={result.url} "
            f"attempts={result.attempt_count} "
            f"error={last_attempt.error_message}"
        )


class WebhookClient:
    """Webhookを再試行付きで送信する。"""

    def __init__(
        self,
        *,
        transport: WebhookTransport | None = None,
        policy: WebhookRetryPolicy | None = None,
        sleeper: Callable[[float], None] = sleep,
    ) -> None:
        """通信処理・再試行条件・待機処理を設定する。"""

        self.transport = (
            transport
            if transport is not None
            else UrlLibWebhookTransport()
        )
        self.policy = policy or WebhookRetryPolicy()
        self.sleeper = sleeper

    def send(
        self,
        request: WebhookRequest,
        *,
        raise_on_failure: bool = True,
    ) -> WebhookDeliveryResult:
        """Webhook送信を最大試行回数まで実行する。"""

        attempts: list[WebhookAttemptResult] = []
        final_response: WebhookResponse | None = None

        for attempt_number in range(
            1,
            self.policy.maximum_attempts + 1,
        ):
            try:
                response = self.transport.post_json(
                    request,
                    timeout_seconds=self.policy.timeout_seconds,
                )
                final_response = response

                if response.is_successful:
                    attempts.append(
                        WebhookAttemptResult(
                            attempt_number=attempt_number,
                            decision=WebhookRetryDecision.SUCCEEDED,
                            status_code=response.status_code,
                            error_message=None,
                        )
                    )
                    return WebhookDeliveryResult(
                        url=request.url,
                        attempts=tuple(attempts),
                        response=response,
                    )

                error_message = (
                    "Webhook送信先が失敗応答を返しました。 "
                    f"status_code={response.status_code}"
                )

                should_retry = (
                    response.status_code
                    in self.policy.retryable_status_codes
                    and attempt_number
                    < self.policy.maximum_attempts
                )

            except Exception as error:
                error_message = (
                    str(error).strip()
                    or type(error).__name__
                )
                should_retry = (
                    attempt_number
                    < self.policy.maximum_attempts
                )

            decision = (
                WebhookRetryDecision.RETRYING
                if should_retry
                else WebhookRetryDecision.FAILED
            )

            attempts.append(
                WebhookAttemptResult(
                    attempt_number=attempt_number,
                    decision=decision,
                    status_code=(
                        final_response.status_code
                        if final_response is not None
                        else None
                    ),
                    error_message=error_message,
                )
            )

            if not should_retry:
                break

            self.sleeper(
                self.policy.backoff_seconds(
                    attempt_number
                )
            )

        result = WebhookDeliveryResult(
            url=request.url,
            attempts=tuple(attempts),
            response=final_response,
        )

        if raise_on_failure:
            raise WebhookDeliveryError(result)

        return result
