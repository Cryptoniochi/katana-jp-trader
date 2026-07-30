"""kabuステーションREST Clientのテスト。"""

import json

import pytest

from app.market.kabu_station_client import (
    KabuStationClient,
    KabuStationClientSettings,
)
from app.market.kabu_station_models import (
    KabuStationResponseError,
    KabuStationSymbol,
)


class FakeTransport:
    def __init__(self) -> None:
        self.calls = []

    def __call__(
        self,
        method,
        url,
        headers,
        body,
        timeout_seconds,
    ):
        self.calls.append(
            (
                method,
                url,
                headers,
                body,
                timeout_seconds,
            )
        )

        if url.endswith("/token"):
            return 200, b'{"Token":"test-token"}'

        return 200, b"{}"


def client(transport) -> KabuStationClient:
    return KabuStationClient(
        settings=KabuStationClientSettings(
            api_password="secret"
        ),
        transport=transport,
    )


def test_issue_token() -> None:
    transport = FakeTransport()
    value = client(transport)

    assert value.issue_token() == "test-token"
    method, url, headers, body, _timeout = (
        transport.calls[0]
    )
    assert method == "POST"
    assert url.endswith("/token")
    assert "X-API-KEY" not in headers
    assert json.loads(body) == {
        "APIPassword": "secret"
    }


def test_register_symbols_uses_api_key() -> None:
    transport = FakeTransport()
    value = client(transport)

    registered = value.register_symbols(
        [
            KabuStationSymbol("7203"),
            KabuStationSymbol("9984"),
        ]
    )

    assert [symbol.code for symbol in registered] == [
        "7203",
        "9984",
    ]
    _method, url, headers, body, _timeout = (
        transport.calls[-1]
    )
    assert url.endswith("/register")
    assert headers["X-API-KEY"] == "test-token"
    assert json.loads(body) == {
        "Symbols": [
            {"Symbol": "7203", "Exchange": 1},
            {"Symbol": "9984", "Exchange": 1},
        ]
    }


def test_register_rejects_more_than_limit() -> None:
    transport = FakeTransport()
    value = KabuStationClient(
        settings=KabuStationClientSettings(
            api_password="secret",
            maximum_registered_symbols=1,
        ),
        transport=transport,
    )

    with pytest.raises(ValueError, match="上限"):
        value.register_symbols(
            [
                KabuStationSymbol("7203"),
                KabuStationSymbol("9984"),
            ]
        )


def test_api_error_raises_response_error() -> None:
    def transport(
        _method,
        _url,
        _headers,
        _body,
        _timeout,
    ):
        return (
            400,
            b'{"Code":4001009,"Message":"bad request"}',
        )

    with pytest.raises(
        KabuStationResponseError,
        match="4001009",
    ):
        client(transport).issue_token()
