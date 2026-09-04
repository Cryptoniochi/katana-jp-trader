"""Sprint 132 Compact Dashboard template contract tests."""

from pathlib import Path

from app.dashboard.dashboard_web_app import TEMPLATE_DIRECTORY


def _desktop() -> str:
    return (Path(TEMPLATE_DIRECTORY) / "dashboard.html").read_text(encoding="utf-8")


def _mobile() -> str:
    return (Path(TEMPLATE_DIRECTORY) / "mobile_dashboard.html").read_text(encoding="utf-8")


def test_desktop_compact_dashboard_keeps_daily_operational_core() -> None:
    content = _desktop()

    assert "Trading Dashboard" in content
    assert "Today's P/L" in content
    assert "Runtime" in content
    assert "Watchlist" in content
    assert "Today's Executions" in content
    assert "Open Positions" in content
    assert "End-of-Day Check" in content

    assert "/api/dashboard/summary" in content
    assert "/api/dashboard/paper-trading-runtime" in content
    assert "/api/dashboard/dynamic-watchlist" in content
    assert "/api/dashboard/strategies" in content
    assert "/api/dashboard/full-day-validation" in content
    assert "/api/dashboard/symbol-names" in content


def test_mobile_compact_dashboard_keeps_daily_operational_core() -> None:
    content = _mobile()

    assert ">Monitor<" in content
    assert "Today's P/L" in content
    assert "Runtime" in content
    assert "Watchlist" in content
    assert "Today's Executions" in content
    assert "Open Positions" in content
    assert "End-of-Day Check" in content

    assert "/api/dashboard/summary" in content
    assert "/api/dashboard/paper-trading-runtime" in content
    assert "/api/dashboard/dynamic-watchlist" in content
    assert "/api/dashboard/strategies" in content
    assert "/api/dashboard/full-day-validation" in content
    assert "/api/dashboard/symbol-names" in content


def test_compact_dashboard_hides_legacy_verbose_panels() -> None:
    desktop = _desktop()
    mobile = _mobile()

    removed_labels = (
        "Strategy Performance Ranking",
        "Performance Ranking",
        "Performance Breakdown",
        "Morning Pre-Flight",
        "Morning Check",
        "Service Uptime",
        "Recovery History",
    )

    for label in removed_labels:
        assert label not in desktop
        assert label not in mobile

    for chart_id in (
        'id="equity-chart"',
        'id="drawdown-chart"',
        'id="daily-pnl-chart"',
        'id="win-rate-chart"',
    ):
        assert chart_id not in desktop


def test_compact_dashboard_preserves_real_execution_semantics() -> None:
    desktop = _desktop()
    mobile = _mobile()

    assert "recent-trades-body" in desktop
    assert "No executions today." in desktop
    assert "executed_at" in desktop

    assert "mobile-trades" in mobile
    assert "No executions today." in mobile
    assert "executed_at" in mobile


def test_compact_dashboard_formats_times_in_jst() -> None:
    desktop = _desktop()
    mobile = _mobile()

    assert 'timeZone:"Asia/Tokyo"' in desktop
    assert 'timeZone:"Asia/Tokyo"' in mobile
