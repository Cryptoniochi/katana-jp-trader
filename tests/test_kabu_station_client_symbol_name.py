"""KabuStationClient.symbol_nameのテスト。"""

from app.market.kabu_station_client import (
    KabuStationClient,
    KabuStationClientSettings,
)
from app.market.kabu_station_models import KabuStationSymbol


def test_symbol_name_reads_board_symbol_name() -> None:
    requests: list[str] = []

    def transport(method, url, headers, body, timeout):
        requests.append(url)

        if url.endswith("/token"):
            return 200, b'{"Token":"token"}'

        return (
            200,
            (
                '{"Symbol":"7203",'
                '"SymbolName":"トヨタ自動車"}'
            ).encode("utf-8"),
        )

    client = KabuStationClient(
        settings=KabuStationClientSettings(
            api_password="secret"
        ),
        transport=transport,
    )

    assert client.symbol_name(
        KabuStationSymbol("7203")
    ) == "トヨタ自動車"
    assert requests[-1].endswith(
        "/board/7203@1"
    )
