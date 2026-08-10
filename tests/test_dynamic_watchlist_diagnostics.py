"""Dynamic Watchlist診断CLIのテスト。"""

from app.run_dynamic_watchlist_diagnostics import build_diagnostics


def test_build_diagnostics_ranks_by_current_watchlist_rule() -> None:
    payload = {
        "selected": [{"code": "9432"}],
        "evaluated": [
            {"code": "7203", "total_score": 60.0, "average_turnover_20d": 5_000_000_000, "exclusion_reasons": []},
            {"code": "9432", "total_score": 61.0, "average_turnover_20d": 4_000_000_000, "exclusion_reasons": []},
            {"code": "6758", "total_score": 60.0, "average_turnover_20d": 6_000_000_000, "exclusion_reasons": []},
        ],
    }
    rows = build_diagnostics(payload)
    assert [row["code"] for row in rows] == ["9432", "6758", "7203"]
    assert rows[0]["selected"] is True
    assert rows[2]["rank"] == 3


def test_exclusion_reasons_are_flattened() -> None:
    payload = {
        "selected": [],
        "evaluated": [
            {
                "code": "9999",
                "total_score": 10.0,
                "average_turnover_20d": 1.0,
                "exclusion_reasons": ["insufficient_volume", "stale_data"],
            }
        ],
    }
    rows = build_diagnostics(payload)
    assert rows[0]["exclusion_reasons"] == "insufficient_volume,stale_data"
