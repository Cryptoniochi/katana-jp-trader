"""KATANA Service Manager状態ファイルを読み込む。"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_STALE_AFTER_SECONDS = 30.0


class KatanaServiceStatusReadError(RuntimeError):
    """Service状態ファイルを読み込めないことを表す。"""


class KatanaServiceStatusReader:
    """Service Managerが出力したJSON状態をDashboardへ渡す。"""

    def __init__(
        self,
        status_path: Path,
        *,
        stale_after_seconds: float = (
            DEFAULT_STALE_AFTER_SECONDS
        ),
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        if stale_after_seconds <= 0:
            raise ValueError(
                "状態の有効期限は0より大きい必要があります。"
            )

        self.status_path = Path(status_path)
        self.stale_after_seconds = stale_after_seconds
        self.now_provider = (
            now_provider
            if now_provider is not None
            else lambda: datetime.now(timezone.utc)
        )

    def read(self) -> dict[str, Any]:
        """現在状態を読み込み、鮮度情報を付けて返す。"""

        if not self.status_path.exists():
            return self._empty_payload(
                message=(
                    "Service Manager status file "
                    "has not been created."
                )
            )

        try:
            payload = json.loads(
                self.status_path.read_text(
                    encoding="utf-8"
                )
            )
        except (
            OSError,
            UnicodeError,
            json.JSONDecodeError,
        ) as error:
            raise KatanaServiceStatusReadError(
                "KATANA Service状態を読み込めませんでした。 "
                f"path={self.status_path}"
            ) from error

        if not isinstance(payload, dict):
            raise KatanaServiceStatusReadError(
                "KATANA Service状態は辞書形式である必要があります。"
            )

        components = payload.get(
            "components",
            [],
        )

        if not isinstance(components, list):
            raise KatanaServiceStatusReadError(
                "componentsは配列形式である必要があります。"
            )

        generated_at = self._parse_datetime(
            payload.get("generated_at")
        )
        age_seconds = (
            max(
                0.0,
                (
                    self._current_time()
                    - generated_at
                ).total_seconds(),
            )
            if generated_at is not None
            else None
        )
        stale = (
            age_seconds is None
            or age_seconds
            > self.stale_after_seconds
        )
        source_state = str(
            payload.get(
                "service_state",
                "unknown",
            )
        )
        effective_state = (
            "stale"
            if stale
            else source_state
        )

        return {
            "available": True,
            "generated_at": (
                generated_at.isoformat()
                if generated_at is not None
                else payload.get("generated_at")
            ),
            "status_age_seconds": age_seconds,
            "stale_after_seconds": (
                self.stale_after_seconds
            ),
            "stale": stale,
            "source_service_state": source_state,
            "service_state": effective_state,
            "kabu_station_readiness": payload.get(
                "kabu_station_readiness",
                "unknown",
            ),
            "service_started_at": payload.get(
                "service_started_at"
            ),
            "uptime_seconds": payload.get(
                "uptime_seconds"
            ),
            "components": [
                self._normalize_component(item)
                for item in components
                if isinstance(item, dict)
            ],
            "recent_events": [
                self._normalize_event(item)
                for item in payload.get(
                    "recent_events",
                    [],
                )
                if isinstance(item, dict)
            ],
            "message": (
                "Service status has become stale."
                if stale
                else None
            ),
        }

    @staticmethod
    def _normalize_component(
        item: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "name": str(
                item.get(
                    "name",
                    "unknown",
                )
            ),
            "state": str(
                item.get(
                    "state",
                    "unknown",
                )
            ),
            "enabled": bool(
                item.get(
                    "enabled",
                    False,
                )
            ),
            "process_id": item.get(
                "process_id"
            ),
            "restart_count": int(
                item.get(
                    "restart_count",
                    0,
                )
            ),
            "last_exit_code": item.get(
                "last_exit_code"
            ),
            "started_at": item.get(
                "started_at"
            ),
            "updated_at": item.get(
                "updated_at"
            ),
            "message": item.get(
                "message"
            ),
        }

    @staticmethod
    def _normalize_event(
        item: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "occurred_at": item.get(
                "occurred_at"
            ),
            "event_type": str(
                item.get(
                    "event_type",
                    "unknown",
                )
            ),
            "component": item.get(
                "component"
            ),
            "message": str(
                item.get(
                    "message",
                    "",
                )
            ),
        }

    def _current_time(self) -> datetime:
        value = self.now_provider()

        if value.tzinfo is None:
            raise ValueError(
                "現在日時にはタイムゾーンが必要です。"
            )

        return value.astimezone(timezone.utc)

    @staticmethod
    def _parse_datetime(
        value: object,
    ) -> datetime | None:
        if value is None:
            return None

        try:
            parsed = datetime.fromisoformat(
                str(value)
            )
        except ValueError:
            return None

        if parsed.tzinfo is None:
            parsed = parsed.replace(
                tzinfo=timezone.utc
            )

        return parsed.astimezone(timezone.utc)

    def _empty_payload(
        self,
        *,
        message: str,
    ) -> dict[str, Any]:
        return {
            "available": False,
            "generated_at": self._current_time().isoformat(),
            "status_age_seconds": None,
            "stale_after_seconds": (
                self.stale_after_seconds
            ),
            "stale": True,
            "source_service_state": "not_running",
            "service_state": "not_running",
            "kabu_station_readiness": "not_checked",
            "service_started_at": None,
            "uptime_seconds": None,
            "components": [],
            "recent_events": [],
            "message": message,
        }
