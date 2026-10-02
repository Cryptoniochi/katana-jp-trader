"""kabuステーション実口座Read-Only経路のテスト。"""

import json
from datetime import datetime, timezone

from app.live.kabu_station_read_only import (
    KabuStationReadOnlyService,
)
from app.market.kabu_station_client import (
    KabuStationClient,
    KabuStationClientSettings,
)


class ReadOnlyTransport:
    def __init__(self):
        self.calls = []

    def __call__(self, method, url, headers, body, timeout):
        self.calls.append((method, url, headers, body, timeout))
        if url.endswith("/token"):
            return 200, b'{"Token":"read-only-token"}'
        if url.endswith("/wallet/cash"):
            return 200, b'{"StockAccountWallet":1000000}'
        if url.endswith("/wallet/margin"):
            return 200, b'{"MarginAccountWallet":2000000}'
        if "/positions?" in url:
            return 200, json.dumps([
                {"ExecutionID": "E1", "Symbol": "7203", "LeavesQty": 100}
            ]).encode()
        if "/orders?" in url:
            return 200, json.dumps([
                {"ID": "O1", "Symbol": "7203", "State": 5}
            ]).encode()
        raise AssertionError(url)


def make_client(transport):
    return KabuStationClient(
        settings=KabuStationClientSettings(api_password="secret"),
        transport=transport,
    )


def test_read_only_endpoints_use_get_and_never_send_order():
    transport = ReadOnlyTransport()
    client = make_client(transport)
    client.issue_token()

    assert client.cash_wallet()["StockAccountWallet"] == 1_000_000
    assert client.margin_wallet()["MarginAccountWallet"] == 2_000_000
    assert client.positions()[0]["Symbol"] == "7203"
    assert client.orders()[0]["ID"] == "O1"

    authenticated = transport.calls[1:]
    assert all(call[0] == "GET" for call in authenticated)
    assert all(call[2]["X-API-KEY"] == "read-only-token" for call in authenticated)
    assert all("sendorder" not in call[1] for call in transport.calls)
    assert all("cancelorder" not in call[1] for call in transport.calls)


def test_service_builds_complete_snapshot_without_exposing_token():
    transport = ReadOnlyTransport()
    snapshot = KabuStationReadOnlyService(
        client=make_client(transport),
        now_provider=lambda: datetime(
            2026, 10, 3, 0, 0, tzinfo=timezone.utc
        ),
    ).collect()

    assert snapshot.state == "complete"
    assert snapshot.connected is True
    assert snapshot.token_issued is True
    assert snapshot.position_count == 1
    assert snapshot.order_count == 1
    assert snapshot.active_order_count == 0
    assert "Token" not in snapshot.to_payload()


def test_service_returns_failed_snapshot_when_token_fails():
    def transport(method, url, headers, body, timeout):
        return 401, b'{"Code":401,"Message":"unauthorized"}'

    snapshot = KabuStationReadOnlyService(
        client=make_client(transport)
    ).collect()

    assert snapshot.state == "failed"
    assert snapshot.connected is False
    assert snapshot.token_issued is False
    assert "token" in snapshot.errors[0]
