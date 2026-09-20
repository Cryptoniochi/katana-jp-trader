"""Operational Readiness UIのテスト。"""

from pathlib import Path

from app.dashboard.dashboard_web_app import (
    TEMPLATE_DIRECTORY,
)


def test_mobile_contains_runtime_health_panel() -> None:
    content = (
        Path(TEMPLATE_DIRECTORY)
        / "mobile_dashboard.html"
    ).read_text(
        encoding="utf-8"
    )

    assert "Runtime" in content
    assert "/api/dashboard/paper-trading-runtime" in content
    assert "mobile-runtime-state" in content


def test_desktop_contains_runtime_health_panel() -> None:
    content = (
        Path(TEMPLATE_DIRECTORY)
        / "dashboard.html"
    ).read_text(
        encoding="utf-8"
    )

    assert "Paper trading and service health" in content
    assert "/api/dashboard/service-status" in content
    assert "runtime-state" in content
