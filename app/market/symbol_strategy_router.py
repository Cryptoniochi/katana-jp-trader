"""銘柄別に有効戦略を解決する。"""

from __future__ import annotations

from dataclasses import dataclass

from app.dynamic_watchlist.strategy_routing_models import (
    StrategyRoutingSnapshot,
)


@dataclass(frozen=True, slots=True)
class StrategyRouteDecision:
    """1銘柄の戦略解決結果。"""

    code: str
    strategy_names: tuple[str, ...]
    routed: bool
    reason: str


class SymbolStrategyRouter:
    """Dynamic Watchlistルートを安全に適用する。"""

    def __init__(
        self,
        snapshot: StrategyRoutingSnapshot,
    ) -> None:
        self.snapshot = snapshot
        self._routes = {
            route.code: route
            for route in snapshot.routes
        }

    def update_snapshot(
        self,
        snapshot: StrategyRoutingSnapshot,
    ) -> None:
        """以後の解決に使うRouting Snapshotを差し替える。"""

        routes = {
            route.code: route
            for route in snapshot.routes
        }
        self.snapshot = snapshot
        self._routes = routes

    def resolve(
        self,
        code: str,
    ) -> StrategyRouteDecision:
        normalized = code.strip()
        route = self._routes.get(normalized)

        if route is None:
            return StrategyRouteDecision(
                code=normalized,
                strategy_names=(
                    self.snapshot
                    .fallback_strategy_names
                ),
                routed=False,
                reason=(
                    "No symbol-specific route; "
                    "fallback strategies are used."
                ),
            )

        return StrategyRouteDecision(
            code=normalized,
            strategy_names=(
                route.strategy_name,
            ),
            routed=True,
            reason=(
                "Dynamic Watchlist preferred "
                f"strategy. tier={route.rating_tier} "
                f"total_score={route.total_score:.2f} "
                f"strategy_score={route.strategy_score:.2f}"
            ),
        )
