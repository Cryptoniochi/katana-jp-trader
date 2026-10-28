"""Daily Report Dashboard UI tests."""

from pathlib import Path

from app.dashboard.dashboard_web_app import TEMPLATE_DIRECTORY


def test_desktop_hides_end_of_day_panel() -> None:
    content = (Path(TEMPLATE_DIRECTORY) / "dashboard.html").read_text(encoding="utf-8")

    assert "End-of-Day Check" not in content
    assert "/api/dashboard/full-day-validation" not in content
    assert "full-day-state" not in content


def test_mobile_hides_end_of_day_panel() -> None:
    content = (Path(TEMPLATE_DIRECTORY) / "mobile_dashboard.html").read_text(encoding="utf-8")

    assert "End-of-Day Check" not in content
    assert "/api/dashboard/full-day-validation" not in content
    assert "mobile-full-day-state" not in content
