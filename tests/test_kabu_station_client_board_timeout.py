import json

from app.market.kabu_station_client import (
    KabuStationClient,
    KabuStationClientSettings,
)
from app.market.kabu_station_models import KabuStationSymbol


def test_board_timeout_override_does_not_change_default_timeout():
    observed = []

    def transport(method, url, headers, body, timeout_seconds):
        observed.append((method, url, timeout_seconds))
        if url.endswith("/token"):
            return 200, json.dumps({"Token": "TOKEN"}).encode("utf-8")
        return 200, b"{}"

    client = KabuStationClient(
        settings=KabuStationClientSettings(
            api_password="password",
            timeout_seconds=4.0,
        ),
        transport=transport,
    )

    client.issue_token()
    client.board(
        KabuStationSymbol(code="7203", exchange=1),
        timeout_seconds=0.75,
    )
    client.board(
        KabuStationSymbol(code="6758", exchange=1),
    )

    assert observed[0][2] == 4.0
    assert observed[1][2] == 0.75
    assert observed[2][2] == 4.0


def test_board_timeout_override_must_be_positive():
    def transport(method, url, headers, body, timeout_seconds):
        if url.endswith("/token"):
            return 200, json.dumps({"Token": "TOKEN"}).encode("utf-8")
        return 200, b"{}"

    client = KabuStationClient(
        settings=KabuStationClientSettings(
            api_password="password",
        ),
        transport=transport,
    )
    client.issue_token()

    try:
        client.board(
            KabuStationSymbol(code="7203", exchange=1),
            timeout_seconds=0,
        )
    except ValueError as error:
        assert "0より大きい" in str(error)
    else:
        raise AssertionError("ValueError was not raised")
