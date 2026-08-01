"""Performance Breakdown UIのテスト。"""

from pathlib import Path

from app.dashboard.dashboard_web_app import (
    TEMPLATE_DIRECTORY,
)


def test_desktop_contains_breakdown_ui() -> None:
    content = (
        Path(TEMPLATE_DIRECTORY)
        / "dashboard.html"
    ).read_text(
        encoding="utf-8"
    )

    assert "Performance Breakdown" in content
    assert "/api/dashboard/performance-breakdown" in content
    assert "breakdown-weekday" in content


def test_mobile_contains_breakdown_ui() -> None:
    content = (
        Path(TEMPLATE_DIRECTORY)
        / "mobile_dashboard.html"
    ).read_text(
        encoding="utf-8"
    )

    assert "Performance Breakdown" in content
    assert "mobile-breakdown-tabs" in content
    assert "/api/dashboard/performance-breakdown" in content
