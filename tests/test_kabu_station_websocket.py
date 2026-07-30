"""kabuステーションWebSocket Clientのテスト。"""

import json

from app.market.kabu_station_websocket import (
    KabuStationWebSocketClient,
    ReconnectPolicy,
)


class FakeWebSocketApp:
    def __init__(self, callbacks):
        self.callbacks = callbacks
        self.closed = False

    def run_forever(self, **_kwargs):
        self.callbacks["on_open"](self)
        self.callbacks["on_message"](
            self,
            json.dumps(
                {
                    "Symbol": "7203",
                    "CurrentPrice": 2500,
                }
            ),
        )
        self.closed = True
        return True

    def close(self):
        self.closed = True


def test_websocket_parses_json_message() -> None:
    messages = []
    states = []

    def factory(_url, **callbacks):
        return FakeWebSocketApp(callbacks)

    client = KabuStationWebSocketClient(
        on_message=messages.append,
        on_state_change=lambda state, detail: (
            states.append((state, detail))
        ),
        websocket_factory=factory,
        reconnect_policy=ReconnectPolicy(
            initial_delay_seconds=0.01,
            maximum_delay_seconds=0.01,
            jitter_ratio=0,
        ),
        sleep=lambda _seconds: client._stop_event.set(),
    )

    client.run()

    assert messages == [
        {
            "Symbol": "7203",
            "CurrentPrice": 2500,
        }
    ]
    assert ("connected", None) in states


def test_reconnect_policy_is_capped() -> None:
    policy = ReconnectPolicy(
        initial_delay_seconds=1,
        maximum_delay_seconds=4,
        multiplier=2,
        jitter_ratio=0,
    )

    assert policy.delay_for_attempt(0) == 1
    assert policy.delay_for_attempt(1) == 2
    assert policy.delay_for_attempt(2) == 4
    assert policy.delay_for_attempt(5) == 4
