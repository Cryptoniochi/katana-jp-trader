"""ExecutionNotificationServiceのテスト。"""

from datetime import datetime, timezone

from app.notifications.execution_notification_service import (
    ExecutionNotificationService,
)
from app.trading.order_models import OrderSide
from app.trading.signal_models import SignalAction
from app.trading.trade_execution_models import (
    TradeExecution,
    TradeExecutionRecord,
)


NOW = datetime(
    2026,
    7,
    21,
    0,
    15,
    tzinfo=timezone.utc,
)


class FakeGateway:
    def __init__(self) -> None:
        self.requests = []
        self.continue_on_error_values = []

    def send(
        self,
        request,
        *,
        continue_on_error=True,
    ):
        self.requests.append(request)
        self.continue_on_error_values.append(
            continue_on_error
        )
        return object()


class FakeSignalRecord:
    def __init__(self, action) -> None:
        self.action = action


class FakeSignalProvider:
    def __init__(self, action) -> None:
        self.action = action
        self.signal_ids = []

    def get(self, signal_id):
        self.signal_ids.append(signal_id)
        return FakeSignalRecord(self.action)


def make_record(
    *,
    side=OrderSide.BUY,
) -> TradeExecutionRecord:
    return TradeExecutionRecord(
        id=1,
        execution=TradeExecution(
            execution_id="broker-1:100",
            signal_id="signal-1",
            order_id="order-1",
            broker_order_id="broker-1",
            code="7203",
            side=side,
            quantity=100,
            execution_price=2965.0,
            executed_at=NOW,
            broker_name="paper",
            commission=100.0,
            slippage=25.0,
        ),
        created_at=NOW,
        updated_at=NOW,
    )


def test_buy_execution_notification() -> None:
    gateway = FakeGateway()
    provider = FakeSignalProvider(
        SignalAction.BUY
    )
    service = ExecutionNotificationService(
        gateway=gateway,
        signal_provider=provider,
    )

    service.record(make_record())

    request = gateway.requests[0]

    assert request.context["code"] == "7203"
    assert "BUY" in request.context["message"]
    assert "2,965.00円" in request.context["message"]
    assert request.metadata["action"] == "buy"
    assert gateway.continue_on_error_values == [True]


def test_exit_is_distinguished_from_sell_side() -> None:
    gateway = FakeGateway()
    provider = FakeSignalProvider(
        SignalAction.EXIT
    )
    service = ExecutionNotificationService(
        gateway=gateway,
        signal_provider=provider,
    )

    service.record(
        make_record(
            side=OrderSide.SELL
        )
    )

    request = gateway.requests[0]

    assert "EXIT" in request.context["message"]
    assert request.metadata["action"] == "exit"
    assert request.metadata["side"] == "sell"
