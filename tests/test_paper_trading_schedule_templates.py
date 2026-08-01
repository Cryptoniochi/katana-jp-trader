"""Paper Trading Schedule UIのテスト。"""

from pathlib import Path

from app.dashboard.dashboard_web_app import (
    TEMPLATE_DIRECTORY,
)


def test_mobile_contains_schedule_panel() -> None:
    content = (
        Path(TEMPLATE_DIRECTORY)
        / "mobile_dashboard.html"
    ).read_text(
        encoding="utf-8"
    )

    assert "Today's Schedule" in content
    assert "/api/dashboard/paper-trading-schedule" in content


def test_desktop_contains_schedule_panel() -> None:
    content = (
        Path(TEMPLATE_DIRECTORY)
        / "dashboard.html"
    ).read_text(
        encoding="utf-8"
    )

    assert "Today's Paper Trading Schedule" in content
    assert "/api/dashboard/paper-trading-schedule" in content
