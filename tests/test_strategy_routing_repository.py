"""Dynamic Watchlist戦略ルーティングRepositoryテスト。"""

import json
from pathlib import Path

from app.dynamic_watchlist.strategy_routing_repository import (
    DynamicWatchlistStrategyRoutingRepository,
)


def test_loads_preferred_strategy_routes(
    tmp_path: Path,
) -> None:
    report = tmp_path / "latest.json"
    report.write_text(
        json.dumps(
            {
                "generated_at": (
                    "2026-08-03T08:20:00+09:00"
                ),
                "selected": [
                    {
                        "code": "7203",
                        "rating_tier": "B",
                        "total_score": 57.4,
                        "preferred_strategy": "pullback",
                        "orb_score": 3.1,
                        "pullback_score": 6.8,
                        "high_breakout_score": 1.4,
                    },
                    {
                        "code": "9984",
                        "rating_tier": "C",
                        "total_score": 25.14,
                        "preferred_strategy": "orb",
                        "orb_score": 0.9,
                        "pullback_score": 0.0,
                        "high_breakout_score": 0.1,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    snapshot = (
        DynamicWatchlistStrategyRoutingRepository(
            report_path=report
        ).load()
    )

    assert snapshot.route_count == 2
    assert snapshot.route_for(
        "7203"
    ).strategy_name == "pullback"
    assert snapshot.route_for(
        "9984"
    ).strategy_name == "orb"


def test_minimum_tier_filters_lower_candidates(
    tmp_path: Path,
) -> None:
    report = tmp_path / "latest.json"
    report.write_text(
        json.dumps(
            {
                "selected": [
                    {
                        "code": "7203",
                        "rating_tier": "B",
                        "total_score": 57.4,
                        "preferred_strategy": "pullback",
                        "pullback_score": 6.8,
                    },
                    {
                        "code": "9984",
                        "rating_tier": "C",
                        "total_score": 25.14,
                        "preferred_strategy": "orb",
                        "orb_score": 0.9,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    snapshot = (
        DynamicWatchlistStrategyRoutingRepository(
            report_path=report,
            minimum_rating_tier="B",
        ).load()
    )

    assert snapshot.route_count == 1
    assert snapshot.routes[0].code == "7203"
