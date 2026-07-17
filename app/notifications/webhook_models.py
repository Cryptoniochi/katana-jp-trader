"""外部Webhook通知の共通モデル。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class WebhookRetryDecision(StrEnum):
    """Webhook試行結果。"""

    SUCCEEDED = "succeeded"
    RETRYING = "retrying"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class WebhookRetryPolicy:
    """Webhook送信の再試行条件。"""

    maximum_attempts: int = 3
    initial_backoff_seconds: float = 1.0
    backoff_multiplier: float = 2.0
    maximum_backoff_seconds: float = 30.0
    timeout_seconds: float = 10.0
    retryable_status_codes: frozenset[int] = frozenset(
        {408, 425, 429, 500, 502, 503, 504}
    )

    def __post_init__(self) -> None:
        """再試行設定を検証する。"""

        if self.maximum_attempts <= 0:
            raise ValueError(
                "最大試行回数は0より大きい必要があります。"
            )

        if self.initial_backoff_seconds < 0:
            raise ValueError(
                "初期待機秒数は0以上である必要があります。"
            )

        if self.backoff_multiplier < 1.0:
            raise ValueError(
                "待機倍率は1以上である必要があります。"
            )

        if self.maximum_backoff_seconds < 0:
            raise ValueError(
                "最大待機秒数は0以上である必要があります。"
            )

        if self.timeout_seconds <= 0:
            raise ValueError(
                "タイムアウト秒数は0より大きい必要があります。"
            )

        normalized_codes = frozenset(
            int(code)
            for code in self.retryable_status_codes
        )

        if any(
            code < 100 or code > 599
            for code in normalized_codes
        ):
            raise ValueError(
                "HTTPステータスコードは100以上599以下で"
                "指定してください。"
            )

        object.__setattr__(
            self,
            "retryable_status_codes",
            normalized_codes,
        )

    def backoff_seconds(
        self,
        attempt_number: int,
    ) -> float:
        """指定試行後の待機秒数を返す。"""

        if attempt_number <= 0:
            raise ValueError(
                "試行番号は0より大きい必要があります。"
            )

        backoff = (
            self.initial_backoff_seconds
            * self.backoff_multiplier
            ** (attempt_number - 1)
        )

        return min(
            backoff,
            self.maximum_backoff_seconds,
        )


@dataclass(frozen=True, slots=True)
class WebhookResponse:
    """Webhook送信先からの応答。"""

    status_code: int
    body: str = ""

    def __post_init__(self) -> None:
        """HTTP応答を検証する。"""

        if not 100 <= self.status_code <= 599:
            raise ValueError(
                "HTTPステータスコードは100以上599以下で"
                "ある必要があります。"
            )

    @property
    def is_successful(self) -> bool:
        """2xx応答か返す。"""

        return 200 <= self.status_code < 300


@dataclass(frozen=True, slots=True)
class WebhookAttemptResult:
    """1回のWebhook送信結果。"""

    attempt_number: int
    decision: WebhookRetryDecision
    status_code: int | None
    error_message: str | None

    def __post_init__(self) -> None:
        """試行結果の整合性を検証する。"""

        if self.attempt_number <= 0:
            raise ValueError(
                "試行番号は0より大きい必要があります。"
            )

        normalized_error = (
            None
            if self.error_message is None
            else self.error_message.strip()
        )

        if (
            self.decision is WebhookRetryDecision.SUCCEEDED
            and normalized_error
        ):
            raise ValueError(
                "成功結果にはエラーを設定できません。"
            )

        if (
            self.decision is not WebhookRetryDecision.SUCCEEDED
            and not normalized_error
        ):
            raise ValueError(
                "失敗・再試行結果にはエラーが必要です。"
            )

        object.__setattr__(
            self,
            "error_message",
            normalized_error or None,
        )


@dataclass(frozen=True, slots=True)
class WebhookDeliveryResult:
    """Webhook送信全体の結果。"""

    url: str
    attempts: tuple[WebhookAttemptResult, ...]
    response: WebhookResponse | None

    def __post_init__(self) -> None:
        """送信結果を検証する。"""

        normalized_url = self.url.strip()

        if not normalized_url:
            raise ValueError(
                "Webhook URLを指定してください。"
            )

        if not self.attempts:
            raise ValueError(
                "Webhook送信結果には1件以上の試行が必要です。"
            )

        object.__setattr__(
            self,
            "url",
            normalized_url,
        )

    @property
    def succeeded(self) -> bool:
        """最終送信が成功したか返す。"""

        return (
            self.response is not None
            and self.response.is_successful
            and self.attempts[-1].decision
            is WebhookRetryDecision.SUCCEEDED
        )

    @property
    def attempt_count(self) -> int:
        """試行回数を返す。"""

        return len(self.attempts)


@dataclass(frozen=True, slots=True)
class WebhookRequest:
    """Webhook送信要求。"""

    url: str
    payload: dict[str, Any]
    headers: dict[str, str]

    def __post_init__(self) -> None:
        """送信要求を検証・正規化する。"""

        normalized_url = self.url.strip()

        if not normalized_url:
            raise ValueError(
                "Webhook URLを指定してください。"
            )

        if not isinstance(self.payload, dict):
            raise TypeError(
                "Webhook Payloadは辞書形式で指定してください。"
            )

        if not isinstance(self.headers, dict):
            raise TypeError(
                "Webhook Headersは辞書形式で指定してください。"
            )

        object.__setattr__(self, "url", normalized_url)
        object.__setattr__(self, "payload", dict(self.payload))
        object.__setattr__(self, "headers", dict(self.headers))
