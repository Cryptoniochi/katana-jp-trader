"""Domain Eventをリアルタイム運用ログへ変換する購読ハンドラー。"""

from __future__ import annotations

from app.events.domain_events import (
    DomainEvent,
    DomainEventType,
)
from app.live.live_operation_log_models import (
    LiveLogEventType,
    LiveLogLevel,
    LiveOperationLogEntry,
)
from app.live.live_operation_log_service import (
    LiveOperationLogService,
)


class LiveOperationLogSubscriber:
    """Domain Eventを運用ログへ変換して保存する。"""

    def __init__(
        self,
        *,
        service: LiveOperationLogService,
        event_types: frozenset[DomainEventType] | None = None,
    ) -> None:
        """ログ保存サービスと対象イベントを設定する。"""

        self.service = service
        self.event_types = (
            event_types
            if event_types is not None
            else frozenset(DomainEventType)
        )

    def __call__(self, event: DomainEvent) -> None:
        """Event Busハンドラーとしてログを保存する。"""

        if event.event_type not in self.event_types:
            return

        entry = LiveOperationLogEntry(
            occurred_at=event.occurred_at,
            level=self._level(event),
            event_type=self._event_type(event),
            message=self._message(event),
            cycle_number=self._cycle_number(event),
            code=self._code(event),
            metadata={
                "event_id": event.event_id,
                "domain_event_type": event.event_type.value,
                "source": event.source,
                "correlation_id": event.correlation_id,
                **event.payload,
            },
        )

        self.service.append(entry)

    @staticmethod
    def _level(
        event: DomainEvent,
    ) -> LiveLogLevel:
        """Domain Eventからログレベルを判定する。"""

        if event.event_type is DomainEventType.ERROR_OCCURRED:
            severity = event.payload.get("severity")

            if severity == "critical":
                return LiveLogLevel.CRITICAL

            return LiveLogLevel.ERROR

        if event.event_type is DomainEventType.RISK_ASSESSED:
            decision = event.payload.get("decision")

            if decision == "halted":
                return LiveLogLevel.CRITICAL

            if decision == "rejected":
                return LiveLogLevel.WARNING

        if event.event_type is DomainEventType.RECOVERY_COMPLETED:
            if event.payload.get("has_errors"):
                return LiveLogLevel.WARNING

        return LiveLogLevel.INFO

    @staticmethod
    def _event_type(
        event: DomainEvent,
    ) -> LiveLogEventType:
        """Domain Eventを既存の運用ログ種別へ対応付ける。"""

        mapping = {
            DomainEventType.SIGNAL_CREATED: LiveLogEventType.SIGNAL,
            DomainEventType.RISK_ASSESSED: LiveLogEventType.RISK,
            DomainEventType.ORDER_CREATED: LiveLogEventType.ORDER,
            DomainEventType.ORDER_UPDATED: LiveLogEventType.ORDER,
            DomainEventType.EXECUTION_RECORDED: (
                LiveLogEventType.EXECUTION
            ),
            DomainEventType.ERROR_OCCURRED: LiveLogEventType.ERROR,
        }

        return mapping.get(
            event.event_type,
            LiveLogEventType.RUN_COMPLETED,
        )

    @staticmethod
    def _message(
        event: DomainEvent,
    ) -> str:
        """ログメッセージを作成する。"""

        message = event.payload.get("message")

        if isinstance(message, str) and message.strip():
            return message.strip()

        return (
            f"Domain event received: "
            f"{event.event_type.value}"
        )

    @staticmethod
    def _cycle_number(
        event: DomainEvent,
    ) -> int | None:
        """Payloadからサイクル番号を取得する。"""

        raw_value = event.payload.get("cycle_number")

        if raw_value is None:
            return None

        try:
            value = int(raw_value)
        except (TypeError, ValueError) as error:
            raise ValueError(
                "cycle_numberは整数で指定してください。"
            ) from error

        if value <= 0:
            raise ValueError(
                "cycle_numberは0より大きい必要があります。"
            )

        return value

    @staticmethod
    def _code(
        event: DomainEvent,
    ) -> str | None:
        """Payloadから銘柄コードを取得する。"""

        raw_value = event.payload.get("code")

        if raw_value is None:
            return None

        return str(raw_value)
