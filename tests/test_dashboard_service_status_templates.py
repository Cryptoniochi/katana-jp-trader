"""Dashboard Service Status UIのテスト。"""

from pathlib import Path

from app.dashboard.dashboard_web_app import (
    TEMPLATE_DIRECTORY,
)


def test_desktop_contains_service_status_panel() -> None:
    content = (
        Path(TEMPLATE_DIRECTORY)
        / "dashboard.html"
    ).read_text(
        encoding="utf-8"
    )

    assert "KATANA Service Status" in content
    assert "/api/dashboard/service-status" in content
    assert "service-components" in content


def test_mobile_contains_service_status_panel() -> None:
    content = (
        Path(TEMPLATE_DIRECTORY)
        / "mobile_dashboard.html"
    ).read_text(
        encoding="utf-8"
    )

    assert "KATANA Service" in content
    assert "/api/dashboard/service-status" in content
    assert "mobile-service-components" in content
