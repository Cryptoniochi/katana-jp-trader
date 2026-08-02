"""Dynamic Watchlist結果をDashboard向けに読み込む。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class DynamicWatchlistStatusReader:
    """Dynamic Watchlistの最新レポートを整形する。"""

    def __init__(
        self,
        *,
        latest_report_path: Path,
        schedule_status_path: Path,
    ) -> None:
        self.latest_report_path = Path(
            latest_report_path
        )
        self.schedule_status_path = Path(
            schedule_status_path
        )

    def read(self) -> dict[str, Any]:
        """Dashboard API用Payloadを返す。"""

        report = self._read_json(
            self.latest_report_path
        )
        schedule = self._read_json(
            self.schedule_status_path
        )

        if report is None and schedule is None:
            return {
                "available": False,
                "generated_at": datetime.now(
                    timezone.utc
                ).isoformat(),
                "schedule_state": "not_available",
                "applied": False,
                "selected_count": 0,
                "evaluated_count": 0,
                "eligible_count": 0,
                "capital_limit": None,
                "purchase_budget": None,
                "message": (
                    "Dynamic Watchlist has not "
                    "reported yet."
                ),
                "candidates": [],
            }

        report = report or {}
        schedule = schedule or {}
        selected = report.get(
            "selected",
            [],
        )
        settings = report.get(
            "settings",
            {},
        )

        candidates = [
            self._normalize_candidate(candidate)
            for candidate in selected
            if isinstance(candidate, dict)
        ]

        return {
            "available": True,
            "generated_at": (
                report.get("generated_at")
                or schedule.get("generated_at")
            ),
            "schedule_state": schedule.get(
                "state",
                "unknown",
            ),
            "applied": bool(
                report.get(
                    "applied",
                    schedule.get("applied", False),
                )
            ),
            "selected_count": len(candidates),
            "evaluated_count": int(
                report.get(
                    "evaluated_count",
                    0,
                )
            ),
            "eligible_count": int(
                report.get(
                    "eligible_count",
                    len(candidates),
                )
            ),
            "capital_limit": settings.get(
                "capital_limit"
            ),
            "purchase_budget": settings.get(
                "purchase_budget"
            ),
            "message": (
                schedule.get("message")
                or report.get("message")
                or "Dynamic Watchlist report loaded."
            ),
            "candidates": candidates,
        }

    @staticmethod
    def _normalize_candidate(
        candidate: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "rank": candidate.get("rank"),
            "code": str(
                candidate.get(
                    "code",
                    "",
                )
            ),
            "rating_tier": candidate.get(
                "rating_tier",
                "C",
            ),
            "selection_tier": candidate.get(
                "selection_tier",
                "fallback",
            ),
            "preferred_strategy": candidate.get(
                "preferred_strategy",
                "unknown",
            ),
            "total_score": candidate.get(
                "total_score",
                0.0,
            ),
            "latest_price": candidate.get(
                "latest_price",
                0.0,
            ),
            "purchase_amount": candidate.get(
                "purchase_amount",
                0.0,
            ),
            "orb_score": candidate.get(
                "orb_score",
                0.0,
            ),
            "pullback_score": candidate.get(
                "pullback_score",
                0.0,
            ),
            "high_breakout_score": candidate.get(
                "high_breakout_score",
                0.0,
            ),
            "liquidity_score": candidate.get(
                "liquidity_score",
                0.0,
            ),
            "relative_volume_score": candidate.get(
                "relative_volume_score",
                candidate.get(
                    "volume_score",
                    0.0,
                ),
            ),
            "volatility_score": candidate.get(
                "volatility_score",
                0.0,
            ),
            "gap_score": candidate.get(
                "gap_score",
                0.0,
            ),
            "vwap_score": candidate.get(
                "vwap_score",
                0.0,
            ),
        }

    @staticmethod
    def _read_json(
        path: Path,
    ) -> dict[str, Any] | None:
        if not path.exists():
            return None

        try:
            payload = json.loads(
                path.read_text(
                    encoding="utf-8"
                )
            )
        except (
            OSError,
            UnicodeError,
            json.JSONDecodeError,
        ):
            return None

        return (
            payload
            if isinstance(payload, dict)
            else None
        )
