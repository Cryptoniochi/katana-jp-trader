"""Mobile Dashboard page tests."""

from fastapi.testclient import TestClient

from app.dashboard.dashboard_web_app import create_dashboard_app


class FakeDashboardService:
    def create_payload(self):
        class Payload:
            def to_dict(self):
                return {
                    "generated_at": None,
                    "snapshot": {},
                }

        return Payload()


def test_mobile_dashboard_page_is_available() -> None:
    client = TestClient(
        create_dashboard_app(
            service=FakeDashboardService(),
        )
    )

    response = client.get("/mobile")

    assert response.status_code == 200
    assert "PROJECT KATANA" in response.text
    assert ">Monitor<" in response.text
    assert "Today's P/L" in response.text
    assert "Runtime" in response.text
    assert "Watchlist" in response.text
    assert "Today's Executions" in response.text
    assert "Open Positions" in response.text
