"""RealtimeSignalEngineの銘柄別戦略Routingテスト。"""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.dynamic_watchlist.strategy_routing_models import (
    StrategyRoutingSnapshot,
    SymbolStrategyRoute,
)
from app.market.models import StockPrice
from app.market.realtime_signal_engine import (
    RealtimeSignalEngine,
)
from app.market.symbol_strategy_router import (
    SymbolStrategyRouter,
)


def snapshot(
    *,
    route_strategy: str = "pullback",
) -> StrategyRoutingSnapshot:
    return StrategyRoutingSnapshot(
        generated_at=datetime.now(timezone.utc),
        source_report_path="latest.json",
        route_count=1,
        routes=(
            SymbolStrategyRoute(
                code="7203",
                strategy_name=route_strategy,
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


def bar(
    code: str = "7203",
) -> StockPrice:
    return StockPrice(
        code=code,
        datetime=datetime(
            2026,
            8,
            3,
            9,
            0,
            tzinfo=timezone.utc,
        ),
        open=1000.0,
        high=1010.0,
        low=990.0,
        close=1005.0,
        volume=100_000,
    )


def test_routed_symbol_uses_preferred_strategy_only() -> None:
    engine = RealtimeSignalEngine(
        enabled_strategy_names=(
            "orb",
            "pullback",
            "high-breakout",
        ),
        symbol_strategy_router=SymbolStrategyRouter(
            snapshot()
        ),
    )

    engine.process((bar(),))

    assert engine.active_strategy_names("7203") == (
        "pullback",
    )
    decision = engine.route_decision("7203")
    assert decision is not None
    assert decision.routed


def test_unrouted_symbol_uses_global_fallback() -> None:
    engine = RealtimeSignalEngine(
        enabled_strategy_names=(
            "orb",
            "pullback",
            "high-breakout",
        ),
        symbol_strategy_router=SymbolStrategyRouter(
            snapshot()
        ),
    )

    engine.process((bar("6758"),))

    assert engine.active_strategy_names("6758") == (
        "orb",
        "pullback",
        "high-breakout",
    )
    assert not engine.route_decision("6758").routed


def test_route_disabled_globally_falls_back_safely() -> None:
    engine = RealtimeSignalEngine(
        enabled_strategy_names=("orb",),
        symbol_strategy_router=SymbolStrategyRouter(
            snapshot(route_strategy="pullback")
        ),
    )

    engine.process((bar(),))

    assert engine.active_strategy_names("7203") == (
        "orb",
    )
    assert not engine.route_decision("7203").routed


def test_reset_removes_route_decision() -> None:
    engine = RealtimeSignalEngine(
        enabled_strategy_names=("orb", "pullback"),
        symbol_strategy_router=SymbolStrategyRouter(
            snapshot()
        ),
    )
    engine.process((bar(),))

    engine.reset("7203")

    assert engine.route_decision("7203") is None


def test_router_rejects_custom_strategy_factory() -> None:
    with pytest.raises(
        ValueError,
        match="標準Strategy Registry",
    ):
        RealtimeSignalEngine(
            strategy_factory=lambda _code: SimpleNamespace(),
            symbol_strategy_router=SymbolStrategyRouter(
                snapshot()
            ),
        )
