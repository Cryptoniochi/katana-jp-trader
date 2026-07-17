"""LINE送信結果をLINE専用例外へ変換する高水準Service。"""

from __future__ import annotations

from app.notifications.line.line_exceptions import (
    LineDeliveryError,
)
from app.notifications.line.line_models import (
    LinePushMessageRequest,
)
from app.notifications.line.line_result import (
    LineDeliveryResult,
)
from app.notifications.line.line_sender import (
    LineMessagingSender,
)


class LineNotificationService:
    """LINE送信を実行し、失敗を標準化する。"""

    def __init__(
        self,
        *,
        sender: LineMessagingSender,
    ) -> None:
        self.sender = sender

    def deliver(
        self,
        request: LinePushMessageRequest,
        *,
        raise_on_failure: bool = True,
    ) -> LineDeliveryResult:
        """LINE通知を送信する。"""

        result = self.sender.send(
            request,
            raise_on_failure=False,
        )

        if not result.succeeded and raise_on_failure:
            raise LineDeliveryError(result)

        return result
