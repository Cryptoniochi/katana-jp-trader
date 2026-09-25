"""市場終了時強制決済のテスト。"""

from datetime import datetime, timezone
from types import SimpleNamespace

from app.runtime.end_of_day_liquidation_service import (
    EndOfDayLiquidationService,
)
from app.trading.broker_adapter import (
    BrokerPosition,
    BrokerPositionSide,
)
from app.trading.signal_models import SignalAction

NOW = datetime(
    2026,
    8,
    4,
    6,
    30,
    tzinfo=timezone.utc,
)


class FakeBroker:
    def __init__(self) -> None:
        self.positions = [
            BrokerPosition(
                code="7203",
                side=BrokerPositionSide.LONG,
                quantity=100,
                average_price=3000.0,
                market_price=3137.0,
                updated_at=NOW,
            ),
            BrokerPosition(
                code="8306",
                side=BrokerPositionSide.LONG,
                quantity=100,
                average_price=3500.0,
                market_price=3520.0,
                updated_at=NOW,
            ),
        ]

    def list_positions(self):
        return list(self.positions)


class FakeQueue:
    def __init__(self) -> None:
        self.signals = []

    def enqueue_signal(
        self,
        signal,
        *,
        order_type,
        continue_on_error,
    ):
        self.signals.append(signal)
        return SimpleNamespace(is_failed=False)


class FakeExecution:
    def __init__(self, broker: FakeBroker) -> None:
        self.broker = broker

    def execute_next(self):
        position = self.broker.positions.pop(0)
        return SimpleNamespace(
            is_failed=False,
            execution_record=SimpleNamespace(
                execution=SimpleNamespace(
                    code=position.code
                )
            ),
        )


class FakePortfolioUpdate:
    def __init__(self) -> None:
        self.records = []

    def apply_execution(
        self,
        execution_record,
        *,
        equity_curve_limit=10_000,
    ):
        self.records.append(execution_record)


def test_close_all_positions_uses_exit_pipeline() -> None:
    broker = FakeBroker()
    queue = FakeQueue()
    portfolio = FakePortfolioUpdate()
    service = EndOfDayLiquidationService(
        broker=broker,
        order_queue_service=queue,
        execution_service=FakeExecution(broker),
        portfolio_update_service=portfolio,
        now_provider=lambda: NOW,
    )

    result = service.close_all_positions()

    assert result.requested_count == 2
    assert result.executed_count == 2
    assert result.remaining_position_count == 0
    assert result.completed
    assert broker.list_positions() == []
    assert len(portfolio.records) == 2
    assert all(
        signal.action is SignalAction.EXIT
        for signal in queue.signals
    )


def test_close_all_positions_tracks_its_order_and_refreshes_positions() -> None:
    broker = FakeBroker()
    broker.positions = broker.positions[:1]
    pending = [
        {"order_id": "unrelated-buy", "code": "8306", "buy": True}
    ]

    class OrderedQueue(FakeQueue):
        def enqueue_signal(self, signal, **kwargs):
            self.signals.append(signal)
            order_id = f"exit-{len(self.signals)}"
            pending.append(
                {
                    "order_id": order_id,
                    "code": signal.code,
                    "buy": False,
                }
            )
            return SimpleNamespace(
                is_failed=False,
                order_record=SimpleNamespace(order_id=order_id),
            )

    class OrderedExecution:
        def execute_next(self):
            item = pending.pop(0)
            code = item["code"]
            if item["buy"]:
                broker.positions.append(
                    BrokerPosition(
                        code=code,
                        side=BrokerPositionSide.LONG,
                        quantity=100,
                        average_price=3500.0,
                        market_price=3520.0,
                        updated_at=NOW,
                    )
                )
            else:
                broker.positions = [
                    position
                    for position in broker.positions
                    if position.code != code
                ]
            return SimpleNamespace(
                is_failed=False,
                order_id=item["order_id"],
                execution_record=SimpleNamespace(
                    execution=SimpleNamespace(code=code)
                ),
            )

    queue = OrderedQueue()
    portfolio = FakePortfolioUpdate()
    result = EndOfDayLiquidationService(
        broker=broker,
        order_queue_service=queue,
        execution_service=OrderedExecution(),
        portfolio_update_service=portfolio,
        now_provider=lambda: NOW,
    ).close_all_positions()

    assert result.requested_count == 2
    assert result.executed_count == 3
    assert result.remaining_position_count == 0
    assert [record.execution.code for record in portfolio.records] == [
        "8306",
        "7203",
        "8306",
    ]
