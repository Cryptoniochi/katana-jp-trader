"""DynamicWatchlistStatusReaderのテスト。"""

import json
from pathlib import Path

from app.dashboard.dynamic_watchlist_status_reader import (
    DynamicWatchlistStatusReader,
)


def test_reader_returns_ranked_candidates(
    tmp_path: Path,
) -> None:
    report = tmp_path / "latest.json"
    schedule = tmp_path / "schedule.json"

    report.write_text(
        json.dumps(
            {
                "generated_at": "2026-08-03T08:20:00+09:00",
                "applied": True,
                "evaluated_count": 107,
                "eligible_count": 5,
                "settings": {
                    "capital_limit": 1_000_000,
                    "purchase_budget": 950_000,
                },
                "selected": [
                    {
                        "code": "7203",
                        "rating_tier": "B",
                        "selection_tier": "fallback",
                        "preferred_strategy": "pullback",
                        "total_score": 57.4,
                        "latest_price": 3137.0,
                        "purchase_amount": 313700,
                        "orb_score": 7.0,
                        "pullback_score": 9.0,
                        "high_breakout_score": 3.0,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    schedule.write_text(
        json.dumps(
            {
                "state": "completed",
                "message": "completed",
            }
        ),
        encoding="utf-8",
    )

    payload = DynamicWatchlistStatusReader(
        latest_report_path=report,
        schedule_status_path=schedule,
    ).read()

    assert payload["available"]
    assert payload["selected_count"] == 1
    assert payload["applied"]
    assert payload["candidates"][0][
        "preferred_strategy"
    ] == "pullback"


def test_reader_returns_unavailable_without_files(
    tmp_path: Path,
) -> None:
    payload = DynamicWatchlistStatusReader(
        latest_report_path=tmp_path / "missing1.json",
        schedule_status_path=tmp_path / "missing2.json",
    ).read()

    assert not payload["available"]
    assert payload["selected_count"] == 0
