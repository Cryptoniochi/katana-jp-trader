"""ティック保護ストップのテスト。"""

from datetime import datetime, timezone

from app.market.market_data_provider import MarketDataTick
from app.market.models import StockPrice
from app.market.realtime_signal_engine import RealtimeSignalEngine
from app.risk.tick_protective_stop import (
    LatestMarketTickBuffer,
    TickProtectiveStopService,
    TickProtectiveStopSettings,
)
from app.trading.broker_adapter import BrokerPosition, BrokerPositionSide


class FakeBroker:
    def __init__(self, positions):
        self.positions = list(positions)

    def list_positions(self):
        return list(self.positions)


class FakeExecutor:
    def __init__(self, *, succeeds=True):
        self.succeeds = succeeds
        self.calls = []

    def execute_external_signal(
        self,
        signal,
        *,
        current_price,
        continue_on_error=False,
    ):
        self.calls.append((signal, current_price, continue_on_error))
        return self.succeeds


class FakeStrategy:
    def __init__(self):
        self.closed = False

    def evaluate(self, frame):
        return ()

    def reset(self):
        self.closed = False

    def mark_position_closed(self):
        self.closed = True


def tick(code: str, price: float, second: int = 0) -> MarketDataTick:
    return MarketDataTick(
        code=code,
        price=price,
        observed_at=datetime(2026, 10, 5, 0, 30, second, tzinfo=timezone.utc),
    )


def position(
    code: str,
    *,
    side: BrokerPositionSide = BrokerPositionSide.LONG,
) -> BrokerPosition:
    return BrokerPosition(
        code=code,
        side=side,
        quantity=100,
        average_price=1_000.0,
        market_price=1_000.0,
    )


def test_buffer_keeps_only_latest_tick_per_code():
    buffer = LatestMarketTickBuffer()
    buffer.accept(tick("7203", 995.0, 1))
    buffer.accept(tick("7203", 990.0, 2))
    buffer.accept(tick("6503", 2_000.0, 1))

    drained = buffer.drain()

    assert [(item.code, item.price) for item in drained] == [
        ("6503", 2_000.0),
        ("7203", 990.0),
    ]
    assert buffer.drain() == ()


def test_long_position_triggers_at_one_percent_loss_and_syncs_strategy():
    buffer = LatestMarketTickBuffer()
    buffer.accept(tick("7203", 990.0))
    executor = FakeExecutor()
    prices = []
    closed = []
    service = TickProtectiveStopService(
        tick_buffer=buffer,
        broker=FakeBroker([position("7203")]),
        signal_executor=executor,
        market_price_updater=lambda code, price: prices.append((code, price)),
        position_closed_notifier=closed.append,
        settings=TickProtectiveStopSettings(stop_loss_rate=0.01),
    )

    result = service.process_pending()

    assert result.triggered_count == 1
    assert result.executed_count == 1
    signal, current_price, continue_on_error = executor.calls[0]
    assert signal.code == "7203"
    assert signal.action.value == "exit"
    assert signal.metadata["exit_reason"] == "tick_protective_stop"
    assert signal.metadata["stop_price"] == 990.0
    assert current_price == 990.0
    assert continue_on_error is True
    assert prices == [("7203", 990.0)]
    assert closed == ["7203"]


def test_non_trigger_and_failed_execution_do_not_sync_strategy():
    buffer = LatestMarketTickBuffer()
    buffer.accept(tick("7203", 991.0))
    buffer.accept(tick("6503", 989.0))
    executor = FakeExecutor(succeeds=False)
    closed = []
    service = TickProtectiveStopService(
        tick_buffer=buffer,
        broker=FakeBroker([position("7203"), position("6503")]),
        signal_executor=executor,
        market_price_updater=lambda code, price: None,
        position_closed_notifier=closed.append,
    )

    result = service.process_pending()

    assert result.triggered_count == 1
    assert result.executed_count == 0
    assert len(executor.calls) == 1
    assert closed == []


def test_short_position_uses_inverse_stop_direction():
    buffer = LatestMarketTickBuffer()
    buffer.accept(tick("7203", 1_010.0))
    executor = FakeExecutor()
    service = TickProtectiveStopService(
        tick_buffer=buffer,
        broker=FakeBroker([
            position("7203", side=BrokerPositionSide.SHORT)
        ]),
        signal_executor=executor,
        market_price_updater=lambda code, price: None,
        position_closed_notifier=lambda code: None,
    )

    result = service.process_pending()

    assert result.executed_count == 1
    assert executor.calls[0][0].metadata["stop_price"] == 1_010.0


def test_signal_engine_forwards_external_position_close():
    strategy = FakeStrategy()
    engine = RealtimeSignalEngine(
        strategy_factory=lambda code: strategy,
        enabled_strategy_names=("orb",),
    )
    engine.process((
        StockPrice(
            code="7203",
            datetime=datetime(2026, 10, 5, 0, 30, tzinfo=timezone.utc),
            open=1_000,
            high=1_001,
            low=999,
            close=1_000,
            volume=1_000,
        ),
    ))

    assert engine.mark_position_closed("7203") is True
    assert strategy.closed is True
    assert engine.mark_position_closed("6503") is False
