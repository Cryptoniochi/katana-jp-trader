"""Daily Report Dashboard UIのテスト。"""

from pathlib import Path

from app.dashboard.dashboard_web_app import (
    TEMPLATE_DIRECTORY,
)


def test_desktop_contains_daily_report_panel() -> None:
    content = (
        Path(TEMPLATE_DIRECTORY)
        / "dashboard.html"
    ).read_text(
        encoding="utf-8"
    )

    assert "Daily Trading Report" in content
    assert "/api/dashboard/daily-report" in content
    assert "daily-report-strategies" in content
    assert "daily-report-symbols" in content


def test_mobile_contains_daily_report_panel() -> None:
    content = (
        Path(TEMPLATE_DIRECTORY)
        / "mobile_dashboard.html"
    ).read_text(
        encoding="utf-8"
    )

    assert "Daily Report" in content
    assert "/api/dashboard/daily-report" in content
    assert "mobile-daily-report-strategies" in content
    assert "mobile-daily-report-symbols" in content
