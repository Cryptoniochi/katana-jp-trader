"""Morning Pre-Flight状態をDashboard向けに読み込む。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class MorningPreflightStatusReader:
    """Morning Pre-Flightスケジュールと検証結果を統合する。"""

    def __init__(
        self,
        *,
        schedule_status_path: Path,
        operation_report_path: Path,
    ) -> None:
        self.schedule_status_path = Path(
            schedule_status_path
        )
        self.operation_report_path = Path(
            operation_report_path
        )

    def read(self) -> dict[str, Any]:
        """Dashboard API用Payloadを返す。"""

        schedule = self._read_json(
            self.schedule_status_path
        )
        report = self._read_json(
            self.operation_report_path
        )

        if schedule is None and report is None:
            return {
                "available": False,
                "generated_at": datetime.now(
                    timezone.utc
                ).isoformat(),
                "schedule_state": "not_available",
                "overall_state": "unknown",
                "ready_for_trading": False,
                "target_date": None,
                "next_action_at": None,
                "last_attempt_at": None,
                "last_exit_code": None,
                "message": (
                    "Morning Pre-Flight has not "
                    "reported yet."
                ),
                "checks": [],
            }

        schedule = schedule or {}
        report = report or {}
        checks = report.get(
            "checks",
            [],
        )

        return {
            "available": True,
            "generated_at": (
                schedule.get("generated_at")
                or report.get("generated_at")
            ),
            "schedule_state": schedule.get(
                "state",
                "unknown",
            ),
            "overall_state": report.get(
                "overall_state",
                "unknown",
            ),
            "ready_for_trading": bool(
                report.get(
                    "ready_for_next_business_day",
                    False,
                )
            ),
            "target_date": schedule.get(
                "target_date"
            ),
            "next_action_at": schedule.get(
                "next_action_at"
            ),
            "last_attempt_at": schedule.get(
                "last_attempt_at"
            ),
            "last_exit_code": schedule.get(
                "last_exit_code"
            ),
            "message": (
                schedule.get("message")
                or "Morning Pre-Flight report loaded."
            ),
            "checks": [
                dict(check)
                for check in checks
                if isinstance(check, dict)
            ],
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
