"""kabuステーションRealtime Providerのテスト。"""

from datetime import datetime, timezone

from app.market.kabu_station_realtime_provider import (
    KabuStationRealtimeProvider,
)


class FakeClient:
    def __init__(self) -> None:
        self.registered_symbols = ()

    def issue_token(self):
        return "token"

    def register_symbols(self, symbols):
        self.registered_symbols = tuple(symbols)
        return self.registered_symbols

    def unregister_all(self):
        self.registered_symbols = ()


def test_provider_connects_and_registers_codes() -> None:
    provider = KabuStationRealtimeProvider(
        client=FakeClient()
    )

    assert provider.connect() == "token"
    assert provider.register_codes(
        ["7203", "9984"]
    ) == ("7203", "9984")

    status = provider.status()
    assert status.is_connected
    assert status.registered_codes == (
        "7203",
        "9984",
    )


def test_provider_records_message_and_disconnect() -> None:
    provider = KabuStationRealtimeProvider(
        client=FakeClient()
    )
    observed_at = datetime.now(timezone.utc)

    provider.record_message_received(observed_at)
    assert provider.status().last_message_at == observed_at

    provider.record_disconnected("socket closed")
    status = provider.status()
    assert not status.is_connected
    assert status.last_error == "socket closed"
