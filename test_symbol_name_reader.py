"""kabuステーション銘柄名Cacheのテスト。"""

from pathlib import Path

from app.dashboard.symbol_name_reader import SymbolNameReader
from app.market.kabu_station_models import KabuStationSymbol


class FakeClient:
    def __init__(self) -> None:
        self.requested: list[str] = []

    def symbol_name(
        self,
        symbol: KabuStationSymbol,
    ) -> str | None:
        self.requested.append(symbol.code)
        return {
            "7203": "トヨタ自動車",
            "8306": "三菱ＵＦＪフィナンシャル・グループ",
        }.get(symbol.code)


def test_reader_fetches_and_caches_names(
    tmp_path: Path,
) -> None:
    client = FakeClient()
    reader = SymbolNameReader(
        tmp_path / "data" / "katana.db",
        cache_path=tmp_path / "symbol_names.json",
        client=client,
        request_interval_seconds=0,
    )

    names = reader.resolve(
        ["7203", "8306"]
    )

    assert names["7203"] == "トヨタ自動車"
    assert names["8306"].startswith("三菱ＵＦＪ")
    assert client.requested == ["7203", "8306"]

    cached = reader.read_all()
    assert cached == names


def test_reader_uses_cache_without_api_call(
    tmp_path: Path,
) -> None:
    client = FakeClient()
    reader = SymbolNameReader(
        tmp_path / "data" / "katana.db",
        cache_path=tmp_path / "symbol_names.json",
        client=client,
        request_interval_seconds=0,
    )
    reader.resolve(["7203"])
    client.requested.clear()

    assert reader.resolve(["7203"]) == {
        "7203": "トヨタ自動車"
    }
    assert client.requested == []
