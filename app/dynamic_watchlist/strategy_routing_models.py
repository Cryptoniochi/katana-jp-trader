"""Dynamic Watchlistによる銘柄別戦略ルーティングモデル。"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any


SUPPORTED_STRATEGIES = frozenset(
    {
        "orb",
        "pullback",
        "high-breakout",
    }
)


@dataclass(frozen=True, slots=True)
class SymbolStrategyRoute:
    """1銘柄に割り当てる戦略。"""

    code: str
    strategy_name: str
    rating_tier: str
    total_score: float
    strategy_score: float
    source_generated_at: datetime | None = None

    def __post_init__(self) -> None:
        normalized_code = self.code.strip()

        if not normalized_code.isdigit():
            raise ValueError(
                "銘柄コードは数字で指定してください。"
            )

        if len(normalized_code) not in {4, 5}:
            raise ValueError(
                "銘柄コードは4桁または5桁です。"
            )

        if self.strategy_name not in SUPPORTED_STRATEGIES:
            raise ValueError(
                "未対応の戦略です。"
                f" strategy={self.strategy_name}"
            )

        if self.total_score < 0:
            raise ValueError(
                "総合スコアは0以上です。"
            )

        if self.strategy_score < 0:
            raise ValueError(
                "戦略スコアは0以上です。"
            )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["source_generated_at"] = (
            self.source_generated_at.isoformat()
            if self.source_generated_at is not None
            else None
        )
        return payload


@dataclass(frozen=True, slots=True)
class StrategyRoutingSnapshot:
    """Dynamic Watchlistから構築したルーティング表。"""

    generated_at: datetime
    source_report_path: str
    route_count: int
    routes: tuple[SymbolStrategyRoute, ...]
    fallback_strategy_names: tuple[str, ...]

    def route_for(
        self,
        code: str,
    ) -> SymbolStrategyRoute | None:
        normalized = code.strip()

        for route in self.routes:
            if route.code == normalized:
                return route

        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at.isoformat(),
            "source_report_path": self.source_report_path,
            "route_count": self.route_count,
            "routes": [
                route.to_dict()
                for route in self.routes
            ],
            "fallback_strategy_names": list(
                self.fallback_strategy_names
            ),
        }
