"""Learning反映済みWatchlistのRoutingテスト。"""

import json
from pathlib import Path

from app.dynamic_watchlist.strategy_routing_repository import (
    DynamicWatchlistStrategyRoutingRepository,
)


def test_routing_uses_feedback_adjusted_preference(
    tmp_path: Path,
) -> None:
    report = tmp_path / "latest.json"
    report.write_text(
        json.dumps(
            {
                "generated_at": "2026-08-03T08:20:00+09:00",
                "selected": [
                    {
                        "code": "7203",
                        "rating_tier": "A",
                        "total_score": 70.0,
                        "technical_score": 58.0,
                        "historical_score": 12.0,
                        "learning_applied": True,
                        "learned_preferred_strategy": "pullback",
                        "preferred_strategy": "pullback",
                        "orb_score": 7.0,
                        "pullback_score": 6.0,
                        "high_breakout_score": 2.0,
                    }
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

    route = snapshot.route_for("7203")

    assert route is not None
    assert route.strategy_name == "pullback"
