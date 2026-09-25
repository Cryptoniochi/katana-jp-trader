"""Sprint 127 dashboard symbol-name regression tests."""

from pathlib import Path

from fastapi.testclient import TestClient

from app.dashboard.dashboard_web_app import create_dashboard_app
from app.dashboard.symbol_name_reader import SymbolNameReader


def test_symbol_label_source_is_available() -> None:
    reader = SymbolNameReader(
        Path("data/katana.db")
    )
    assert hasattr(reader, "resolve")
    assert hasattr(reader, "read_all")


def test_symbol_name_api_keeps_cached_names_without_open_positions() -> None:
    class DashboardService:
        def create_payload(self):
            class Payload:
                def to_dict(self):
                    return {
                        "generated_at": None,
                        "snapshot": {"portfolio": None},
                    }

            return Payload()

    class CachedSymbolReader:
        def read_all(self):
            return {"7203": "トヨタ自動車"}

        def resolve(self, codes):
            assert tuple(codes) == ()
            return {}

    response = TestClient(
        create_dashboard_app(
            service=DashboardService(),
            symbol_name_reader=CachedSymbolReader(),
        )
    ).get("/api/dashboard/symbol-names")

    assert response.status_code == 200
    assert response.json() == {
        "count": 1,
        "names": {"7203": "トヨタ自動車"},
    }


def test_watchlist_api_includes_symbol_names_directly() -> None:
    class DashboardService:
        def create_payload(self):
            class Payload:
                def to_dict(self):
                    return {
                        "generated_at": None,
                        "snapshot": {"portfolio": None},
                    }

            return Payload()

    class WatchlistReader:
        def read(self):
            return {
                "available": True,
                "candidates": [{"code": "6861"}],
            }

    class SymbolReader:
        def read_all(self):
            return {}

        def resolve(self, codes):
            assert tuple(codes) == ("6861",)
            return {"6861": "キーエンス"}

    response = TestClient(
        create_dashboard_app(
            service=DashboardService(),
            dynamic_watchlist_reader=WatchlistReader(),
            symbol_name_reader=SymbolReader(),
        )
    ).get("/api/dashboard/dynamic-watchlist")

    assert response.status_code == 200
    assert response.json()["candidates"][0]["name"] == (
        "キーエンス"
    )


def test_strategy_api_includes_symbol_names_directly() -> None:
    class DashboardService:
        def create_payload(self):
            class Payload:
                def to_dict(self):
                    return {
                        "generated_at": None,
                        "snapshot": {"portfolio": None},
                    }

            return Payload()

    class StrategyService:
        def create_payload(self):
            class Payload:
                def to_dict(self):
                    return {
                        "recent_trades": [{"code": "7201"}],
                        "recent_completed_trades": [],
                    }

            return Payload()

    class SymbolReader:
        def read_all(self):
            return {}

        def resolve(self, codes):
            assert tuple(codes) == ("7201",)
            return {"7201": "日産自動車"}

    response = TestClient(
        create_dashboard_app(
            service=DashboardService(),
            strategy_service=StrategyService(),
            symbol_name_reader=SymbolReader(),
        )
    ).get("/api/dashboard/strategies")

    assert response.status_code == 200
    assert response.json()["recent_trades"][0]["name"] == (
        "日産自動車"
    )
