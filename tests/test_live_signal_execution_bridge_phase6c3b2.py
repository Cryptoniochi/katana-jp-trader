from datetime import date, datetime, timezone

import pytest

from app.live.live_signal_execution_bridge import (
    FinalLiveEntrySubmitter,
    LiveRealtimeSignalIntentProvider,
    LiveSignalBridgeError,
)
from app.market.realtime_signal_models import (
    RealtimeSignalDecision,
    RealtimeSignalProcessResult,
)
from app.trading.order_models import OrderSide, OrderType
from app.trading.signal_models import SignalAction, TradeSignal

DAY = date(2026, 10, 14)
NOW = datetime(2026, 10, 14, 0, 5, tzinfo=timezone.utc)


def _signal(signal_id="sig-1", *, action=SignalAction.BUY, code="7203", quantity=100):
    return TradeSignal(
        signal_id=signal_id,
        code=code,
        strategy_name="orb",
        action=action,
        generated_at=NOW,
        signal_price=2500.0,
        quantity=quantity,
        reason="test",
    )


def _result(*signals):
    return RealtimeSignalProcessResult(
        decision=(
            RealtimeSignalDecision.SIGNALS_GENERATED
            if signals
            else RealtimeSignalDecision.BAR_PROCESSED
        ),
        input_bar_count=1,
        processed_bar_count=1,
        skipped_duplicate_count=0,
        signal_count=len(signals),
        signals=tuple(signals),
    )


class Engine:
    def __init__(self, result):
        self.result = result
        self.prices = None

    def process(self, prices):
        self.prices = tuple(prices)
        return self.result


def test_realtime_buy_signal_becomes_live_entry_intent():
    engine = Engine(_result(_signal()))
    provider = LiveRealtimeSignalIntentProvider(
        signal_engine=engine,
        price_provider=lambda: ("bar-1",),
    )
    intents = provider()
    assert engine.prices == ("bar-1",)
    assert len(intents) == 1
    assert intents[0].execution_key == "sig-1"
    assert intents[0].code == "7203"
    assert intents[0].quantity == 100
    assert intents[0].side == "BUY"
    assert provider.last_result is engine.result


def test_no_signal_returns_no_live_entry_intent():
    provider = LiveRealtimeSignalIntentProvider(
        signal_engine=Engine(_result()),
        price_provider=lambda: (),
    )
    assert provider() == ()


@pytest.mark.parametrize("action", [SignalAction.SELL, SignalAction.EXIT])
def test_sell_or_exit_signal_fails_closed_in_entry_bridge(action):
    provider = LiveRealtimeSignalIntentProvider(
        signal_engine=Engine(_result(_signal(action=action))),
        price_provider=lambda: (),
    )
    with pytest.raises(LiveSignalBridgeError, match="protective-exit"):
        provider()


def test_duplicate_execution_key_in_one_cycle_fails_closed():
    provider = LiveRealtimeSignalIntentProvider(
        signal_engine=Engine(_result(_signal(), _signal())),
        price_provider=lambda: (),
    )
    with pytest.raises(LiveSignalBridgeError, match="Duplicate execution key"):
        provider()


def test_final_submitter_builds_deterministic_market_buy_and_requires_flat_baseline():
    calls = []

    class Flow:
        def submit(self, **kwargs):
            calls.append(kwargs)
            return "started"

    submitter = FinalLiveEntrySubmitter(prepared_tracking_flow=Flow())
    from app.live.live_production_runner import LiveEntryIntent

    intent = LiveEntryIntent("sig-1", "7203", 100)
    assert submitter(intent, DAY) == "started"
    assert len(calls) == 1
    call = calls[0]
    assert call["execution_key"] == "sig-1"
    assert call["trading_date"] == DAY
    assert call["required_baseline_quantity"] == 0
    order = call["order"]
    assert order.signal_id == "sig-1"
    assert order.code == "7203"
    assert order.quantity == 100
    assert order.side is OrderSide.BUY
    assert order.order_type is OrderType.MARKET
    assert order.limit_price is None
    assert order.stop_price is None
    assert order.order_id.startswith("live-")


def test_same_execution_key_generates_same_order_id():
    class Flow:
        def __init__(self):
            self.orders = []

        def submit(self, **kwargs):
            self.orders.append(kwargs["order"])
            return object()

    flow = Flow()
    submitter = FinalLiveEntrySubmitter(prepared_tracking_flow=flow)
    from app.live.live_production_runner import LiveEntryIntent

    intent = LiveEntryIntent("same-key", "7203", 100)
    submitter(intent, DAY)
    submitter(intent, DAY)
    assert flow.orders[0].order_id == flow.orders[1].order_id


def test_submitter_does_not_swallow_prepared_flow_block():
    class Flow:
        def submit(self, **kwargs):
            raise RuntimeError("daily loss / kill switch / safety blocked")

    submitter = FinalLiveEntrySubmitter(prepared_tracking_flow=Flow())
    from app.live.live_production_runner import LiveEntryIntent

    with pytest.raises(RuntimeError, match="daily loss"):
        submitter(LiveEntryIntent("sig-1", "7203", 100), DAY)
