"""Operational status表示のテスト。"""

from pathlib import Path

from app.dashboard.dashboard_web_app import (
    TEMPLATE_DIRECTORY,
)


def test_mobile_displays_runtime_and_watchlist_status() -> None:
    content = (
        Path(TEMPLATE_DIRECTORY)
        / "mobile_dashboard.html"
    ).read_text(
        encoding="utf-8"
    )

    assert "mobile-runtime-state" in content
    assert "mobile-watchlist-state" in content
    assert "dataset.status" in content


def test_desktop_displays_service_state() -> None:
    content = (
        Path(TEMPLATE_DIRECTORY)
        / "dashboard.html"
    ).read_text(
        encoding="utf-8"
    )

    assert "/api/dashboard/service-status" in content
    assert "service-state" in content
