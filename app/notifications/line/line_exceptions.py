"""LINE Messaging API送信例外。"""

from __future__ import annotations

from app.notifications.line.line_response import (
    LineApiError,
    parse_line_api_error,
)
from app.notifications.line.line_result import (
    LineDeliveryResult,
)


class LineDeliveryError(RuntimeError):
    """LINE通知の全試行失敗を表す。"""

    def __init__(
        self,
        result: LineDeliveryResult,
    ) -> None:
        """送信結果とAPIエラーを保持する。"""

        self.result = result
        self.api_error: LineApiError | None = (
            parse_line_api_error(result.delivery)
        )

        if self.api_error is not None:
            message = self.api_error.message
        else:
            last_attempt = result.delivery.attempts[-1]
            message = (
                last_attempt.error_message
                or "LINE通知に失敗しました。"
            )

        super().__init__(
            "LINE通知に失敗しました。 "
            f"destination_id={result.destination_id} "
            f"attempts={result.attempt_count} "
            f"error={message}"
        )
