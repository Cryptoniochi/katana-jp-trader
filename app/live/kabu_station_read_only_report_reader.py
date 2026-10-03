"""Read-only file provider for saved kabu Station account snapshots.

Phase 6-C Step 4F-1 deliberately performs file I/O only.  It never creates a
kabu Station client, issues a token, calls an HTTP endpoint, or sends an order.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.live.kabu_station_read_only import KabuStationReadOnlySnapshot


class KabuStationReadOnlyReportReader:
    """Reconstruct the latest saved read-only kabu Station snapshot."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def __call__(self) -> KabuStationReadOnlySnapshot | None:
        return self.read()

    def read(self) -> KabuStationReadOnlySnapshot | None:
        if not self.path.exists():
            return None

        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(
                "kabu Station read-only report must be a JSON object."
            )

        return KabuStationReadOnlySnapshot(
            generated_at=self._datetime(payload, "generated_at"),
            state=self._string(payload, "state"),
            connected=self._boolean(payload, "connected"),
            token_issued=self._boolean(payload, "token_issued"),
            cash_wallet=self._optional_mapping(payload, "cash_wallet"),
            margin_wallet=self._optional_mapping(payload, "margin_wallet"),
            positions=self._mapping_tuple(payload, "positions"),
            orders=self._mapping_tuple(payload, "orders"),
            errors=self._string_tuple(payload, "errors"),
        )

    @staticmethod
    def _datetime(payload: dict[str, object], key: str):
        from datetime import datetime

        value = KabuStationReadOnlyReportReader._string(payload, key)
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.tzinfo is None:
            raise ValueError(f"{key} must be timezone-aware.")
        return result

    @staticmethod
    def _string(payload: dict[str, object], key: str) -> str:
        value = payload.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{key} must be a non-empty string.")
        return value.strip()

    @staticmethod
    def _boolean(payload: dict[str, object], key: str) -> bool:
        value = payload.get(key)
        if not isinstance(value, bool):
            raise ValueError(f"{key} must be a boolean.")
        return value

    @staticmethod
    def _optional_mapping(
        payload: dict[str, object],
        key: str,
    ) -> dict[str, object] | None:
        value = payload.get(key)
        if value is None:
            return None
        if not isinstance(value, dict):
            raise ValueError(f"{key} must be an object or null.")
        return dict(value)

    @staticmethod
    def _mapping_tuple(
        payload: dict[str, object],
        key: str,
    ) -> tuple[dict[str, object], ...]:
        value = payload.get(key)
        if not isinstance(value, list):
            raise ValueError(f"{key} must be a list.")
        if not all(isinstance(item, dict) for item in value):
            raise ValueError(f"{key} must contain only objects.")
        return tuple(dict(item) for item in value)

    @staticmethod
    def _string_tuple(
        payload: dict[str, object],
        key: str,
    ) -> tuple[str, ...]:
        value = payload.get(key)
        if not isinstance(value, list):
            raise ValueError(f"{key} must be a list.")
        if not all(isinstance(item, str) for item in value):
            raise ValueError(f"{key} must contain only strings.")
        return tuple(value)
