"""Dashboard可視化Assetのテスト。"""

from pathlib import Path


def test_dashboard_template_contains_visualizations() -> None:
    path = (
        Path("app")
        / "dashboard"
        / "templates"
        / "dashboard.html"
    )
    content = path.read_text(encoding="utf-8")

    assert 'id="equity-chart"' in content
    assert 'id="daily-pl-chart"' in content
    assert 'id="cumulative-pl-chart"' in content
    assert 'id="drawdown-chart"' in content
    assert 'id="daily-win-rate"' in content
    assert 'id="maximum-drawdown"' in content
    assert "window.setInterval(refreshDashboard, 30000)" in content


def test_dashboard_css_supports_chart_grid() -> None:
    path = (
        Path("app")
        / "dashboard"
        / "static"
        / "dashboard.css"
    )
    content = path.read_text(encoding="utf-8")

    assert ".chart-grid" in content
    assert ".line-series" in content
    assert ".bar-chart" in content
    assert ".bar.positive" in content
    assert ".bar.negative" in content
