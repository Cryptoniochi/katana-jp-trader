from pathlib import Path

import pytest


TEMPLATE_DIRECTORY = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "dashboard"
    / "templates"
)


@pytest.mark.parametrize(
    "template_name",
    [
        "dashboard.html",
        "mobile_dashboard.html",
    ],
)
def test_unrealized_pnl_prefers_portfolio_snapshot(
    template_name: str,
) -> None:
    content = (
        TEMPLATE_DIRECTORY / template_name
    ).read_text(encoding="utf-8")

    assert (
        "portfolio.total_unrealized_profit_loss"
        in content
    )


@pytest.mark.parametrize(
    "template_name",
    [
        "dashboard.html",
        "mobile_dashboard.html",
    ],
)
def test_unrealized_pnl_keeps_runtime_fallback(
    template_name: str,
) -> None:
    content = (
        TEMPLATE_DIRECTORY / template_name
    ).read_text(encoding="utf-8")

    assert (
        "runtime.unrealized_profit_loss"
        in content
    )