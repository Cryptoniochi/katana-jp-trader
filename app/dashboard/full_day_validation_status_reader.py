"""Full-Day Validation Dashboard status reader。"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


TOKYO = ZoneInfo("Asia/Tokyo")


class FullDayValidationStatusReader:
    """最新のFull-Day Validation結果をDashboard向けに読む。"""

    def __init__(
        self,
        report_path: Path = Path(
            "reports/service/full_day_validation.json"
        ),
    ) -> None:
        self.report_path = Path(report_path)

    def read(self) -> dict[str, object]:
        if not self.report_path.exists():
            return self._unavailable(
                state="not_yet_validated",
                message=(
                    "Full-Day Validation has not been "
                    "generated yet."
                ),
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
            return self._unavailable(
                state="unavailable",
                message=(
                    "Full-Day Validation report "
                    f"could not be read: {error}"
                ),
            )

        if not isinstance(payload, dict):
            return self._unavailable(
                state="unavailable",
                message=(
                    "Full-Day Validation report "
                    "has an invalid format."
                ),
            )

        trading_date = self._text(
            payload.get("trading_date")
        )
        generated_at = self._text(
            payload.get("generated_at")
        )

        if trading_date is None:
            return self._unavailable(
                state="unavailable",
                message=(
                    "Full-Day Validation report does not "
                    "contain trading_date."
                ),
                generated_at=generated_at,
            )

        normalized = self._normalized_payload(
            payload
        )

        today = datetime.now(TOKYO).date().isoformat()
        if trading_date != today:
            return {
                **normalized,
                "available": True,
                "state": "not_yet_validated",
                "message": (
                    "Today's Full-Day Validation has not "
                    f"been generated yet. Latest: {trading_date}."
                ),
            }

        passed = bool(payload.get("passed"))
        return {
            **normalized,
            "available": True,
            "state": "pass" if passed else "fail",
            "message": (
                "Full-day paper trading validation passed."
                if passed
                else (
                    "Full-day paper trading validation "
                    "detected one or more failures."
                )
            ),
        }

    @classmethod
    def _normalized_payload(
        cls,
        payload: dict[str, Any],
    ) -> dict[str, object]:
        checks = payload.get("checks")
        if not isinstance(checks, list):
            checks = []

        normalized_checks: list[dict[str, object]] = []
        for item in checks:
            if not isinstance(item, dict):
                continue
            normalized_checks.append(
                {
                    "key": cls._text(item.get("key"))
                    or "unknown",
                    "label": cls._text(item.get("label"))
                    or "Unknown",
                    "passed": bool(item.get("passed")),
                    "message": cls._text(
                        item.get("message")
                    ) or "",
                }
            )

        runtime = payload.get("runtime")
        if not isinstance(runtime, dict):
            runtime = {}

        integrity = payload.get("integrity")
        if not isinstance(integrity, dict):
            integrity = {}

        daily_summary = payload.get("daily_summary")
        if not isinstance(daily_summary, dict):
            daily_summary = {}

        daily_report = payload.get("daily_report")
        if not isinstance(daily_report, dict):
            daily_report = {}

        return {
            "generated_at": cls._text(
                payload.get("generated_at")
            ),
            "trading_date": cls._text(
                payload.get("trading_date")
            ),
            "passed": bool(payload.get("passed")),
            "failed_check_count": cls._integer(
                payload.get("failed_check_count")
            ),
            "checks": normalized_checks,
            "runtime": runtime,
            "integrity": integrity,
            "daily_summary": daily_summary,
            "daily_report": daily_report,
        }

    @classmethod
    def _unavailable(
        cls,
        *,
        state: str,
        message: str,
        generated_at: str | None = None,
    ) -> dict[str, object]:
        return {
            "available": False,
            "state": state,
            "generated_at": generated_at,
            "trading_date": None,
            "passed": False,
            "failed_check_count": 0,
            "checks": [],
            "runtime": {},
            "integrity": {},
            "daily_summary": {},
            "daily_report": {},
            "message": message,
        }

    @staticmethod
    def _text(value: Any) -> str | None:
        text = str(value or "").strip()
        return text or None

    @staticmethod
    def _integer(value: Any) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0
