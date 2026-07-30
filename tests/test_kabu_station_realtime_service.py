"""kabuステーションRealtime Serviceのテスト。"""

from app.market.kabu_station_realtime_service import (
    KabuStationRealtimeService,
)


class FakeProvider:
    def __init__(self):
        self.connected = False
        self.codes = ()
        self.messages = []
        self.disconnects = []

    def connect(self):
        self.connected = True
        return "token"

    def register_codes(self, codes):
        self.codes = tuple(codes)
        return self.codes

    def record_message_received(self, observed_at):
        self.messages.append(observed_at)

    def record_disconnected(self, detail):
        self.disconnects.append(detail)


class FakeWebSocketClient:
    def __init__(
        self,
        *,
        on_message,
        on_state_change,
    ):
        self.on_message = on_message
        self.on_state_change = on_state_change
        self.started = False
        self.stopped = False

    def start(self):
        self.started = True
        self.on_state_change("connected", None)

    def stop(self):
        self.stopped = True


def test_service_connects_registers_and_starts() -> None:
    provider = FakeProvider()
    service = KabuStationRealtimeService(
        provider=provider,
        websocket_client_factory=FakeWebSocketClient,
    )

    registered = service.start(
        ["7203", "9984", "7203"]
    )

    assert registered == ("7203", "9984")
    assert provider.connected
    assert provider.codes == ("7203", "9984")
    assert service._websocket_client.started


def test_service_parses_push_and_calls_tick_handler() -> None:
    provider = FakeProvider()
    ticks = []
    service = KabuStationRealtimeService(
        provider=provider,
        websocket_client_factory=FakeWebSocketClient,
        on_tick=ticks.append,
    )
    service.start(["7203"])

    service._on_push_message(
        {
            "Symbol": "7203",
            "Exchange": 1,
            "CurrentPrice": 2500.0,
            "CurrentPriceTime": (
                "2026-07-29T09:01:02+09:00"
            ),
            "TradingVolume": 1000,
        }
    )

    assert len(provider.messages) == 1
    assert len(ticks) == 1
    assert ticks[0].code == "7203"
