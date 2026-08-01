"""Self-Healing Dashboard表示のテスト。"""

from pathlib import Path

from app.dashboard.dashboard_web_app import (
    TEMPLATE_DIRECTORY,
)


def test_desktop_contains_uptime_and_recovery_history() -> None:
    content = (
        Path(TEMPLATE_DIRECTORY)
        / "dashboard.html"
    ).read_text(
        encoding="utf-8"
    )

    assert "Service Uptime" in content
    assert "Recovery History" in content
    assert "service-events" in content


def test_mobile_contains_uptime_and_recovery_history() -> None:
    content = (
        Path(TEMPLATE_DIRECTORY)
        / "mobile_dashboard.html"
    ).read_text(
        encoding="utf-8"
    )

    assert "Service Uptime" in content
    assert "Recovery History" in content
    assert "mobile-service-events" in content
