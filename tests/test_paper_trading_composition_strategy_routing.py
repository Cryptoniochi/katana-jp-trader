"""PaperTradingCompositionのStrategy Routing設定テスト。"""

from pathlib import Path

import pytest

from app.runtime.paper_trading_composition import (
    PaperTradingProductionSettings,
)


def make_settings(
    tmp_path: Path,
    **overrides,
) -> PaperTradingProductionSettings:
    values = {
        "database_path": tmp_path / "katana.db",
        "codes": ("7203",),
        "kabu_station_api_password": "test-password",
        "enabled_strategy_names": (
            "orb",
            "pullback",
            "high-breakout",
        ),
        "strategy_routing_report_path": Path(
            "reports/watchlist/latest.json"
        ),
    }
    values.update(overrides)
    return PaperTradingProductionSettings(**values)


def test_routing_report_path_is_resolved(
    tmp_path: Path,
) -> None:
    settings = make_settings(tmp_path)

    assert settings.strategy_routing_report_path.is_absolute()
    assert settings.strategy_routing_report_path.name == (
        "latest.json"
    )


@pytest.mark.parametrize(
    "tier",
    ["A+", "A", "B", "C"],
)
def test_accepts_supported_minimum_tier(
    tmp_path: Path,
    tier: str,
) -> None:
    settings = make_settings(
        tmp_path,
        strategy_routing_minimum_rating_tier=tier,
    )

    assert (
        settings.strategy_routing_minimum_rating_tier
        == tier
    )


def test_rejects_unknown_minimum_tier(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        ValueError,
        match="最低Tier",
    ):
        make_settings(
            tmp_path,
            strategy_routing_minimum_rating_tier="D",
        )
