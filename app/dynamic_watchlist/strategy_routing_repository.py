"""Dynamic Watchlistレポートから戦略ルートを読み込む。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.dynamic_watchlist.strategy_routing_models import (
    SUPPORTED_STRATEGIES,
    StrategyRoutingSnapshot,
    SymbolStrategyRoute,
)


class DynamicWatchlistStrategyRoutingError(
    RuntimeError
):
    """ルーティング読込失敗。"""


class DynamicWatchlistStrategyRoutingRepository:
    """latest.jsonを銘柄別戦略ルートへ変換する。"""

    def __init__(
        self,
        report_path: Path = Path(
            "reports/watchlist/latest.json"
        ),
        *,
        minimum_rating_tier: str = "C",
        minimum_total_score: float = 0.0,
        fallback_strategy_names: tuple[str, ...] = (
            "orb",
            "pullback",
            "high-breakout",
        ),
        now_provider=None,
    ) -> None:
        self.report_path = Path(report_path)
        self.minimum_rating_tier = (
            minimum_rating_tier
        )
        self.minimum_total_score = float(
            minimum_total_score
        )
        self.fallback_strategy_names = tuple(
            fallback_strategy_names
        )
        self.now_provider = (
            now_provider
            if now_provider is not None
            else lambda: datetime.now(
                timezone.utc
            )
        )

        unknown = set(
            self.fallback_strategy_names
        ) - SUPPORTED_STRATEGIES

        if unknown:
            raise ValueError(
                "未対応のFallback戦略があります。"
                f" strategies={sorted(unknown)}"
            )

        if self.minimum_rating_tier not in {
            "A+",
            "A",
            "B",
            "C",
        }:
            raise ValueError(
                "minimum_rating_tierは"
                "A+、A、B、Cのいずれかです。"
            )

    def load(self) -> StrategyRoutingSnapshot:
        """最新Watchlistからルーティング表を返す。"""

        payload = self._read_payload()
        generated_at = self._parse_datetime(
            payload.get("generated_at")
        )
        selected = payload.get("selected")

        if not isinstance(selected, list):
            raise DynamicWatchlistStrategyRoutingError(
                "Dynamic Watchlist report has no "
                "selected candidate list."
            )

        routes: list[SymbolStrategyRoute] = []

        for candidate in selected:
            route = self._build_route(
                candidate,
                generated_at=generated_at,
            )

            if route is not None:
                routes.append(route)

        return StrategyRoutingSnapshot(
            generated_at=self._current_time(),
            source_report_path=str(
                self.report_path
            ),
            route_count=len(routes),
            routes=tuple(routes),
            fallback_strategy_names=(
                self.fallback_strategy_names
            ),
        )

    def _build_route(
        self,
        candidate: Any,
        *,
        generated_at: datetime | None,
    ) -> SymbolStrategyRoute | None:
        if not isinstance(candidate, dict):
            return None

        code = str(
            candidate.get("code", "")
        ).strip()
        strategy_name = str(
            (
                candidate.get(
                    "preferred_strategy",
                    "",
                )
            )
        ).strip()

        if (
            candidate.get("learning_applied") is True
            and candidate.get(
                "learned_preferred_strategy"
            ) in SUPPORTED_STRATEGIES
        ):
            learned_name = str(
                candidate[
                    "learned_preferred_strategy"
                ]
            )
            adjusted_field = {
                "orb": "orb_score",
                "pullback": "pullback_score",
                "high-breakout": (
                    "high_breakout_score"
                ),
            }[learned_name]
            learned_score = self._to_float(
                candidate.get(
                    "historical_score"
                )
            )
            current_score = self._to_float(
                candidate.get(
                    adjusted_field
                )
            )
            if (
                learned_score is not None
                and learned_score > 0
                and current_score is not None
            ):
                strategy_name = str(
                    candidate.get(
                        "preferred_strategy",
                        learned_name,
                    )
                ).strip()
        rating_tier = str(
            candidate.get(
                "rating_tier",
                "C",
            )
        ).strip()
        total_score = self._to_float(
            candidate.get("total_score")
        )

        if (
            strategy_name not in SUPPORTED_STRATEGIES
            or rating_tier not in {
                "A+",
                "A",
                "B",
                "C",
            }
            or total_score is None
            or not self._tier_is_eligible(
                rating_tier
            )
            or total_score
            < self.minimum_total_score
        ):
            return None

        strategy_score = self._strategy_score(
            candidate,
            strategy_name=strategy_name,
        )

        if strategy_score is None:
            return None

        try:
            return SymbolStrategyRoute(
                code=code,
                strategy_name=strategy_name,
                rating_tier=rating_tier,
                total_score=total_score,
                strategy_score=strategy_score,
                source_generated_at=generated_at,
            )
        except ValueError:
            return None

    def _tier_is_eligible(
        self,
        rating_tier: str,
    ) -> bool:
        ranks = {
            "C": 0,
            "B": 1,
            "A": 2,
            "A+": 3,
        }
        return (
            ranks[rating_tier]
            >= ranks[self.minimum_rating_tier]
        )

    @staticmethod
    def _strategy_score(
        candidate: dict[str, Any],
        *,
        strategy_name: str,
    ) -> float | None:
        field_by_strategy = {
            "orb": "orb_score",
            "pullback": "pullback_score",
            "high-breakout": (
                "high_breakout_score"
            ),
        }
        return (
            DynamicWatchlistStrategyRoutingRepository
            ._to_float(
                candidate.get(
                    field_by_strategy[
                        strategy_name
                    ]
                )
            )
        )

    def _read_payload(self) -> dict[str, Any]:
        if not self.report_path.exists():
            raise DynamicWatchlistStrategyRoutingError(
                "Dynamic Watchlist report does not "
                f"exist: {self.report_path}"
            )

        try:
            payload = json.loads(
                self.report_path.read_text(
                    encoding="utf-8"
                )
            )
        except (
            OSError,
            UnicodeError,
            json.JSONDecodeError,
        ) as error:
            raise DynamicWatchlistStrategyRoutingError(
                "Dynamic Watchlist report cannot "
                "be read."
            ) from error

        if not isinstance(payload, dict):
            raise DynamicWatchlistStrategyRoutingError(
                "Dynamic Watchlist report root "
                "must be an object."
            )

        return payload

    @staticmethod
    def _parse_datetime(
        value: Any,
    ) -> datetime | None:
        if not isinstance(value, str):
            return None

        try:
            parsed = datetime.fromisoformat(
                value
            )
        except ValueError:
            return None

        if parsed.tzinfo is None:
            return parsed.replace(
                tzinfo=timezone.utc
            )

        return parsed

    @staticmethod
    def _to_float(
        value: Any,
    ) -> float | None:
        try:
            return float(value)
        except (
            TypeError,
            ValueError,
        ):
            return None

    def _current_time(self) -> datetime:
        value = self.now_provider()

        if value.tzinfo is None:
            raise ValueError(
                "現在日時にはタイムゾーンが必要です。"
            )

        return value.astimezone(
            timezone.utc
        )
