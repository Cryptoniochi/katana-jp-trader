"""Watchlist-to-Execution Integrity Dashboard status reader。"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


TOKYO = ZoneInfo("Asia/Tokyo")


class WatchlistExecutionIntegrityStatusReader:
    """最新のWatchlist-to-Execution Integrity監査結果を読む。"""

    def __init__(
        self,
        report_path: Path = Path(
            "reports/service/watchlist_execution_integrity.json"
        ),
    ) -> None:
        self.report_path = Path(report_path)

    def read(self) -> dict[str, object]:
        if not self.report_path.exists():
            return self._unavailable(
                state="not_yet_audited",
                message=(
                    "Watchlist-to-Execution Integrity audit "
                    "has not been generated yet."
                ),
            )

        try:
            payload = json.loads(
                self.report_path.read_text(encoding="utf-8")
            )
        except (
            OSError,
            UnicodeError,
            json.JSONDecodeError,
        ) as error:
            return self._unavailable(
                state="unavailable",
                message=(
                    "Watchlist-to-Execution Integrity report "
                    f"could not be read: {error}"
                ),
            )

        if not isinstance(payload, dict):
            return self._unavailable(
                state="unavailable",
                message=(
                    "Watchlist-to-Execution Integrity report "
                    "has an invalid format."
                ),
            )

        trading_date = self._text(payload.get("trading_date"))
        generated_at = self._text(payload.get("generated_at"))

        if trading_date is None:
            return self._unavailable(
                state="unavailable",
                message=(
                    "Watchlist-to-Execution Integrity report "
                    "does not contain trading_date."
                ),
                generated_at=generated_at,
            )

        today = datetime.now(TOKYO).date().isoformat()
        if trading_date != today:
            return {
                **self._normalized_payload(payload),
                "available": True,
                "state": "not_yet_audited",
                "message": (
                    "Today's integrity audit has not been "
                    f"generated yet. Latest audit: {trading_date}."
                ),
            }

        integrity_ok = bool(payload.get("integrity_ok"))
        return {
            **self._normalized_payload(payload),
            "available": True,
            "state": "pass" if integrity_ok else "fail",
            "message": (
                "Watchlist-to-Execution path is consistent."
                if integrity_ok
                else (
                    "Watchlist-to-Execution integrity "
                    "mismatches were detected."
                )
            ),
        }

    @classmethod
    def _normalized_payload(
        cls,
        payload: dict[str, Any],
    ) -> dict[str, object]:
        return {
            "generated_at": cls._text(
                payload.get("generated_at")
            ),
            "trading_date": cls._text(
                payload.get("trading_date")
            ),
            "integrity_ok": bool(
                payload.get("integrity_ok")
            ),
            "trace_available": bool(
                payload.get("trace_available")
            ),
            "selected_count": cls._integer(
                payload.get("selected_count")
            ),
            "loaded_count": cls._integer(
                payload.get("loaded_count")
            ),
            "monitored_count": cls._integer(
                payload.get("monitored_count")
            ),
            "signal_count": cls._integer(
                payload.get("signal_count")
            ),
            "execution_count": cls._integer(
                payload.get("execution_count")
            ),
            "selected_not_loaded_codes": cls._strings(
                payload.get("selected_not_loaded_codes")
            ),
            "loaded_not_monitored_codes": cls._strings(
                payload.get("loaded_not_monitored_codes")
            ),
            "monitored_not_loaded_codes": cls._strings(
                payload.get("monitored_not_loaded_codes")
            ),
            "orphan_signal_codes": cls._strings(
                payload.get("orphan_signal_codes")
            ),
            "orphan_execution_codes": cls._strings(
                payload.get("orphan_execution_codes")
            ),
            "symbols": cls._symbols(payload.get("symbols")),
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
            "integrity_ok": False,
            "trace_available": False,
            "selected_count": 0,
            "loaded_count": 0,
            "monitored_count": 0,
            "signal_count": 0,
            "execution_count": 0,
            "selected_not_loaded_codes": [],
            "loaded_not_monitored_codes": [],
            "monitored_not_loaded_codes": [],
            "orphan_signal_codes": [],
            "orphan_execution_codes": [],
            "symbols": [],
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

    @staticmethod
    def _strings(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [
            str(item).strip()
            for item in value
            if str(item).strip()
        ]

    @classmethod
    def _symbols(cls, value: Any) -> list[dict[str, object]]:
        if not isinstance(value, list):
            return []

        result: list[dict[str, object]] = []
        for item in value:
            if not isinstance(item, dict):
                continue
            code = cls._text(item.get("code"))
            if code is None:
                continue
            result.append(
                {
                    "code": code,
                    "selected": bool(item.get("selected")),
                    "loaded": bool(item.get("loaded")),
                    "monitored": bool(item.get("monitored")),
                    "signal_count": cls._integer(
                        item.get("signal_count")
                    ),
                    "execution_count": cls._integer(
                        item.get("execution_count")
                    ),
                    "status": (
                        cls._text(item.get("status"))
                        or "unknown"
                    ),
                }
            )
        return result
