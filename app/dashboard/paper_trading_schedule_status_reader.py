"""Paper Tradingスケジュール状態を読み込む。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class PaperTradingScheduleStatusReader:
    """スケジュールJSONをDashboard向けに正規化する。"""

    def __init__(
        self,
        status_path: Path,
    ) -> None:
        self.status_path = Path(status_path)

    def read(self) -> dict[str, Any]:
        if not self.status_path.exists():
            return {
                "available": False,
                "generated_at": datetime.now(
                    timezone.utc
                ).isoformat(),
                "state": "not_started",
                "business_day": None,
                "enabled": False,
                "process_id": None,
                "last_exit_code": None,
                "next_action_at": None,
                "message": (
                    "Paper Trading scheduler has not "
                    "reported yet."
                ),
                "settings": {},
            }

        payload = json.loads(
            self.status_path.read_text(
                encoding="utf-8"
            )
        )
        return {
            "available": True,
            "generated_at": payload.get(
                "generated_at"
            ),
            "state": payload.get(
                "state",
                "unknown",
            ),
            "business_day": payload.get(
                "business_day"
            ),
            "enabled": payload.get(
                "enabled",
                False,
            ),
            "process_id": payload.get(
                "process_id"
            ),
            "last_exit_code": payload.get(
                "last_exit_code"
            ),
            "next_action_at": payload.get(
                "next_action_at"
            ),
            "message": payload.get(
                "message"
            ),
            "settings": payload.get(
                "settings",
                {},
            ),
        }
