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
