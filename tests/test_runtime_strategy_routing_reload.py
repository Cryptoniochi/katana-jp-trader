"""Runtime Strategy Routing reloadの回帰テスト。"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.dynamic_watchlist.strategy_routing_models import (
    StrategyRoutingSnapshot,
    SymbolStrategyRoute,
)
from app.dynamic_watchlist.strategy_routing_repository import (
    DynamicWatchlistStrategyRoutingError,
)
from app.market.realtime_signal_engine import RealtimeSignalEngine
from app.market.symbol_strategy_router import SymbolStrategyRouter
from app.runtime.paper_trading_composition import (
    RuntimeStrategyRoutingSynchronizer,
)


def _snapshot(
    *routes: tuple[str, str],
) -> StrategyRoutingSnapshot:
    now = datetime(2026, 9, 5, tzinfo=timezone.utc)
    return StrategyRoutingSnapshot(
        generated_at=now,
        source_report_path="reports/watchlist/latest.json",
        route_count=len(routes),
        routes=tuple(
            SymbolStrategyRoute(
                code=code,
                strategy_name=strategy,
                rating_tier="C",
                total_score=20.0,
                strategy_score=10.0,
                source_generated_at=now,
            )
            for code, strategy in routes
        ),
        fallback_strategy_names=(
            "orb",
            "pullback",
            "high-breakout",
        ),
    )


class _Repository:
    def __init__(self, snapshot=None, error=None):
        self.snapshot = snapshot
        self.error = error
        self.calls = 0

    def load(self):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.snapshot


class _Strategy:
    def __init__(self):
        self.reset_count = 0

    def reset(self):
        self.reset_count += 1


def test_router_snapshot_can_be_replaced():
    router = SymbolStrategyRouter(_snapshot(("7203", "orb")))
    assert router.resolve("7203").strategy_names == ("orb",)

    router.update_snapshot(_snapshot(("7203", "pullback")))

    assert router.resolve("7203").strategy_names == ("pullback",)


def test_engine_invalidates_only_changed_effective_routes():
    old_router = SymbolStrategyRouter(
        _snapshot(("7203", "orb"), ("8306", "pullback"))
    )
    engine = RealtimeSignalEngine(
        enabled_strategy_names=("orb", "pullback"),
        symbol_strategy_router=old_router,
    )
    unchanged = _Strategy()
    changed = _Strategy()
    engine._strategies["7203"] = unchanged
    engine._strategies["8306"] = changed
    engine._route_decisions["7203"] = engine._resolve_route("7203")
    engine._route_decisions["8306"] = engine._resolve_route("8306")

    changed_codes = engine.update_symbol_strategy_router(
        SymbolStrategyRouter(
            _snapshot(("7203", "orb"), ("8306", "orb"))
        )
    )

    assert changed_codes == ("8306",)
    assert engine._strategies["7203"] is unchanged
    assert "8306" not in engine._strategies
    assert unchanged.reset_count == 0
    assert changed.reset_count == 1


def test_engine_preserves_bar_and_duplicate_state_when_route_changes():
    engine = RealtimeSignalEngine(
        enabled_strategy_names=("orb", "pullback"),
        symbol_strategy_router=SymbolStrategyRouter(
            _snapshot(("7203", "orb"))
        ),
    )
    engine._strategies["7203"] = _Strategy()
    engine._route_decisions["7203"] = engine._resolve_route("7203")
    marker = datetime(2026, 9, 5, 9, 5, tzinfo=timezone.utc)
    engine._bars_by_code["7203"].append(object())
    engine._last_processed_at["7203"] = marker

    engine.update_symbol_strategy_router(
        SymbolStrategyRouter(_snapshot(("7203", "pullback")))
    )

    assert len(engine._bars_by_code["7203"]) == 1
    assert engine._last_processed_at["7203"] == marker


def test_synchronizer_keeps_old_snapshot_when_report_is_invalid():
    old = _snapshot(("7203", "orb"))
    engine = RealtimeSignalEngine(
        enabled_strategy_names=("orb", "pullback"),
        symbol_strategy_router=SymbolStrategyRouter(old),
    )
    repository = _Repository(
        error=DynamicWatchlistStrategyRoutingError("broken")
    )
    synchronizer = RuntimeStrategyRoutingSynchronizer(
        repository=repository,
        signal_engine=engine,
        current_snapshot=old,
        fail_open=True,
    )

    assert synchronizer.synchronize() is old
    assert engine.symbol_strategy_router.resolve(
        "7203"
    ).strategy_names == ("orb",)


def test_synchronizer_raises_when_fail_open_is_disabled():
    engine = RealtimeSignalEngine(
        enabled_strategy_names=("orb", "pullback")
    )
    synchronizer = RuntimeStrategyRoutingSynchronizer(
        repository=_Repository(
            error=DynamicWatchlistStrategyRoutingError("broken")
        ),
        signal_engine=engine,
        fail_open=False,
    )

    with pytest.raises(DynamicWatchlistStrategyRoutingError):
        synchronizer.synchronize()


def test_same_effective_snapshot_does_not_replace_router():
    current = _snapshot(("7203", "orb"))
    router = SymbolStrategyRouter(current)
    engine = RealtimeSignalEngine(
        enabled_strategy_names=("orb", "pullback"),
        symbol_strategy_router=router,
    )
    synchronizer = RuntimeStrategyRoutingSynchronizer(
        repository=_Repository(_snapshot(("7203", "orb"))),
        signal_engine=engine,
        current_snapshot=current,
    )

    synchronizer.synchronize()

    assert engine.symbol_strategy_router is router


def test_changed_snapshot_updates_router():
    current = _snapshot(("7203", "orb"))
    updated = _snapshot(("7203", "pullback"))
    engine = RealtimeSignalEngine(
        enabled_strategy_names=("orb", "pullback"),
        symbol_strategy_router=SymbolStrategyRouter(current),
    )
    synchronizer = RuntimeStrategyRoutingSynchronizer(
        repository=_Repository(updated),
        signal_engine=engine,
        current_snapshot=current,
    )

    result = synchronizer.synchronize()

    assert result is updated
    assert engine.symbol_strategy_router.resolve(
        "7203"
    ).strategy_names == ("pullback",)
