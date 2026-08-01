"""Operational Readiness UIのテスト。"""

from pathlib import Path

from app.dashboard.dashboard_web_app import (
    TEMPLATE_DIRECTORY,
)


def test_mobile_contains_readiness_panel() -> None:
    content = (
        Path(TEMPLATE_DIRECTORY)
        / "mobile_dashboard.html"
    ).read_text(
        encoding="utf-8"
    )

    assert "Operational Readiness" in content
    assert "/api/dashboard/operational-readiness" in content
    assert "mobile-readiness-checks" in content


def test_desktop_contains_readiness_panel() -> None:
    content = (
        Path(TEMPLATE_DIRECTORY)
        / "dashboard.html"
    ).read_text(
        encoding="utf-8"
    )

    assert "Operational Readiness" in content
    assert "/api/dashboard/operational-readiness" in content
    assert "readiness-checks" in content
