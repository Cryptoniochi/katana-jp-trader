"""Dynamic Watchlist Dashboard UIのテスト。"""

from pathlib import Path

from app.dashboard.dashboard_web_app import (
    TEMPLATE_DIRECTORY,
)


def test_mobile_template_contains_dynamic_watchlist() -> None:
    content = (
        Path(TEMPLATE_DIRECTORY)
        / "mobile_dashboard.html"
    ).read_text(
        encoding="utf-8"
    )

    assert "Dynamic Watchlist" in content
    assert "/api/dashboard/dynamic-watchlist" in content
    assert "dynamic-watchlist-candidates" in content


def test_desktop_template_contains_dynamic_watchlist() -> None:
    content = (
        Path(TEMPLATE_DIRECTORY)
        / "dashboard.html"
    ).read_text(
        encoding="utf-8"
    )

    assert "Dynamic Watchlist" in content
    assert "/api/dashboard/dynamic-watchlist" in content
    assert "desktop-dynamic-candidates" in content
