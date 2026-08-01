"""Dashboard Performance Ranking UIのテスト。"""

from pathlib import Path

from app.dashboard.dashboard_web_app import (
    TEMPLATE_DIRECTORY,
)


def test_desktop_template_contains_performance_ranking() -> None:
    content = (
        Path(TEMPLATE_DIRECTORY)
        / "dashboard.html"
    ).read_text(
        encoding="utf-8"
    )

    assert "Strategy Performance Ranking" in content
    assert "/api/dashboard/performance" in content
    assert "performance-ranking" in content


def test_mobile_template_contains_performance_ranking() -> None:
    content = (
        Path(TEMPLATE_DIRECTORY)
        / "mobile_dashboard.html"
    ).read_text(
        encoding="utf-8"
    )

    assert "Performance Ranking" in content
    assert "/api/dashboard/performance" in content
    assert "mobile-performance-ranking" in content
