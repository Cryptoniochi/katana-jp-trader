"""Dashboardは取引中の最新Runtimeポジションを優先する。"""

from pathlib import Path


TEMPLATE_DIRECTORY = (
    Path(__file__).parents[1]
    / "app"
    / "dashboard"
    / "templates"
)


def test_desktop_prioritizes_runtime_position_valuation() -> None:
    content = (
        TEMPLATE_DIRECTORY / "dashboard.html"
    ).read_text(encoding="utf-8")

    assert (
        "runtime.unrealized_profit_loss??"
        "portfolio.total_unrealized_profit_loss"
        in content
    )
    assert (
        "runtimeToday&&Array.isArray(runtime.positions)"
        "?runtime.positions:(portfolio.positions??[])"
        in content
    )
    assert "renderPositions(currentPositions,names)" in content


def test_mobile_prioritizes_runtime_position_valuation() -> None:
    content = (
        TEMPLATE_DIRECTORY / "mobile_dashboard.html"
    ).read_text(encoding="utf-8")

    assert (
        "runtime.unrealized_profit_loss??"
        "portfolio.total_unrealized_profit_loss"
        in content
    )
    assert (
        "runtimeToday&&Array.isArray(runtime.positions)"
        "?runtime.positions:(portfolio.positions??[])"
        in content
    )
