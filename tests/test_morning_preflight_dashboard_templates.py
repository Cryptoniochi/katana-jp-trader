"""Morning Pre-Flight Dashboard UIのテスト。"""

from pathlib import Path

from app.dashboard.dashboard_web_app import (
    TEMPLATE_DIRECTORY,
)


def test_mobile_template_contains_morning_check() -> None:
    content = (
        Path(TEMPLATE_DIRECTORY)
        / "mobile_dashboard.html"
    ).read_text(
        encoding="utf-8"
    )

    assert "Morning Check" in content
    assert "/api/dashboard/morning-preflight" in content
    assert "morning-preflight-checks" in content


def test_desktop_template_contains_morning_check() -> None:
    content = (
        Path(TEMPLATE_DIRECTORY)
        / "dashboard.html"
    ).read_text(
        encoding="utf-8"
    )

    assert "Morning Pre-Flight" in content
    assert "/api/dashboard/morning-preflight" in content
    assert "desktop-morning-checks" in content
