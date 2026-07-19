"""約定レコードを外部通知へ変換する。"""

from __future__ import annotations

from typing import Protocol

from app.notifications.notification_gateway import (
    NotificationGateway,
)
from app.notifications.notification_gateway_models import (
    NotificationGatewayRequest,
)
from app.notifications.notification_models import (
    NotificationSeverity,
)
from app.notifications.notification_template import (
    NotificationTemplateName,
)
from app.trading.signal_models import SignalAction
from app.trading.trade_execution_models import (
    TradeExecutionRecord,
)


class ExecutionSignalProvider(Protocol):
    """約定元シグナルを取得するRepository互換処理。"""

    def get(self, signal_id: str):
        """シグナルIDに対応する保存済みシグナルを返す。"""


class ExecutionNotificationService:
    """新規約定をNotification Gatewayへ配信する。"""

    def __init__(
        self,
        *,
        gateway: NotificationGateway,
        signal_provider: ExecutionSignalProvider,
    ) -> None:
        self.gateway = gateway
        self.signal_provider = signal_provider

    def record(
        self,
        execution_record: TradeExecutionRecord,
    ) -> None:
        """約定内容と元シグナルを使って通知を送る。"""

        execution = execution_record.execution
        signal_record = self.signal_provider.get(
            execution.signal_id
        )
        action = signal_record.action

        title = self._title(
            action=action,
            code=execution.code,
        )
        message = self._message(
            execution_record=execution_record,
            action=action,
        )

        self.gateway.send(
            NotificationGatewayRequest(
                notification_id=(
                    "execution-"
                    f"{execution.execution_id}"
                ),
                template_name=(
                    NotificationTemplateName.EXECUTION
                ),
                created_at=execution.executed_at,
                source="trade-execution",
                context={
                    "code": execution.code,
                    "message": message,
                },
                severity=NotificationSeverity.INFO,
                metadata={
                    "event_type": "trade_execution",
                    "code": execution.code,
                    "action": action.value,
                    "side": execution.side.value,
                    "quantity": execution.quantity,
                    "execution_price": (
                        execution.execution_price
                    ),
                    "order_id": execution.order_id,
                    "signal_id": execution.signal_id,
                    "execution_id": (
                        execution.execution_id
                    ),
                },
            ),
            continue_on_error=True,
        )

    @staticmethod
    def _title(
        *,
        action: SignalAction,
        code: str,
    ) -> str:
        labels = {
            SignalAction.BUY: "BUY Execution",
            SignalAction.SELL: "SELL Execution",
            SignalAction.EXIT: "EXIT Execution",
        }
        return f"{labels[action]}: {code}"

    @staticmethod
    def _message(
        *,
        execution_record: TradeExecutionRecord,
        action: SignalAction,
    ) -> str:
        execution = execution_record.execution

        return (
            f"Action: {action.value.upper()}\n"
            f"Code: {execution.code}\n"
            f"Quantity: {execution.quantity:,}\n"
            "Execution Price: "
            f"{execution.execution_price:,.2f}円\n"
            "Gross Value: "
            f"{execution.gross_value:,.2f}円\n"
            f"Commission: {execution.commission:,.2f}円\n"
            f"Slippage: {execution.slippage:,.2f}円\n"
            "Executed At: "
            f"{execution.executed_at.isoformat()}\n"
            f"Broker: {execution.broker_name}"
        )
