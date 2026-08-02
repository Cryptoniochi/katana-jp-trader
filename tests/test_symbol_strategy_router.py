"""SymbolStrategyRouterテスト。"""

from datetime import datetime, timezone

from app.dynamic_watchlist.strategy_routing_models import (
    StrategyRoutingSnapshot,
    SymbolStrategyRoute,
)
from app.market.symbol_strategy_router import (
    SymbolStrategyRouter,
)


def build_router() -> SymbolStrategyRouter:
    return SymbolStrategyRouter(
        StrategyRoutingSnapshot(
            generated_at=datetime.now(
                timezone.utc
            ),
            source_report_path="latest.json",
            route_count=1,
            routes=(
                SymbolStrategyRoute(
                    code="7203",
                    strategy_name="pullback",
                    rating_tier="B",
                    total_score=57.4,
                    strategy_score=6.8,
                ),
            ),
            fallback_strategy_names=(
                "orb",
                "pullback",
                "high-breakout",
            ),
        )
    )


def test_routed_symbol_uses_one_strategy() -> None:
    decision = build_router().resolve("7203")

    assert decision.routed
    assert decision.strategy_names == (
        "pullback",
    )


def test_unrouted_symbol_uses_safe_fallback() -> None:
    decision = build_router().resolve("6758")

    assert not decision.routed
    assert decision.strategy_names == (
        "orb",
        "pullback",
        "high-breakout",
    )
