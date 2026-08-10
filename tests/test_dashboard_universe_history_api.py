"""Universe History Dashboard APIのテスト。"""

from fastapi.testclient import TestClient

from app.dashboard.dashboard_web_app import create_dashboard_app


class FakePayload:
    generated_at = None
    daily_history = []
    def to_dict(self):
        return {"generated_at": None, "snapshot": {}, "daily_history": []}


class FakeDashboardService:
    def create_payload(self):
        return FakePayload()


class FakeUniverseHistoryReader:
    def read(self):
        return {
            "available": True,
            "active_universe_count": 3706,
            "symbols_with_1_day": 3679,
            "symbols_with_5_days": 120,
            "symbols_with_10_days": 50,
            "symbols_with_20_days": 10,
            "fallback_count": 3629,
            "developing_count": 40,
            "strict_count": 10,
            "no_history_count": 27,
            "latest_market_data_date": "2026-08-07",
            "coverage_1_day": 0.992714,
            "coverage_5_days": 0.03238,
            "coverage_10_days": 0.013491,
            "coverage_20_days": 0.002698,
        }


def test_universe_history_endpoint() -> None:
    app = create_dashboard_app(
        service=FakeDashboardService(),
        universe_history_reader=FakeUniverseHistoryReader(),
    )
    response = TestClient(app).get("/api/dashboard/universe-history")
    assert response.status_code == 200
    payload = response.json()
    assert payload["active_universe_count"] == 3706
    assert payload["developing_count"] == 40
    assert payload["strict_count"] == 10


def test_universe_history_endpoint_without_reader() -> None:
    app = create_dashboard_app(service=FakeDashboardService())
    response = TestClient(app).get("/api/dashboard/universe-history")
    assert response.status_code == 200
    assert response.json()["available"] is False
