"""Fail-closed reader for durable manual Kill Switch state."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from app.live.live_manual_kill_switch_state import (
    MANUAL_KILL_SWITCH_SCHEMA_VERSION,
    ManualKillSwitchState,
)


class ManualKillSwitchStateReader:
    """Read operator state without mutating anything or accessing the network."""

    _EXPECTED_KEYS = {
        "schema_version",
        "manual_blocked",
        "updated_at",
        "reason",
    }

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def read_state(self) -> ManualKillSwitchState:
        """Return saved state; missing/invalid state fails closed."""

        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            return self._parse_payload(payload)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return self._fail_closed_state()

    def manual_blocked(self) -> bool:
        """Provider consumed by live safety composition."""

        return self.read_state().manual_blocked

    @classmethod
    def _parse_payload(cls, payload: object) -> ManualKillSwitchState:
        if not isinstance(payload, dict):
            raise ValueError("Manual Kill Switch state must be a JSON object.")
        if set(payload) != cls._EXPECTED_KEYS:
            raise ValueError("Manual Kill Switch state schema mismatch.")
        if payload["schema_version"] != MANUAL_KILL_SWITCH_SCHEMA_VERSION:
            raise ValueError("Unsupported Manual Kill Switch schema version.")
        if type(payload["manual_blocked"]) is not bool:
            raise ValueError("manual_blocked must be boolean.")
        if not isinstance(payload["updated_at"], str):
            raise ValueError("updated_at must be an ISO-8601 string.")
        if not isinstance(payload["reason"], str):
            raise ValueError("reason must be a string.")

        updated_at = datetime.fromisoformat(
            payload["updated_at"].replace("Z", "+00:00")
        )
        return ManualKillSwitchState(
            manual_blocked=payload["manual_blocked"],
            updated_at=updated_at,
            reason=payload["reason"],
        )

    @staticmethod
    def _fail_closed_state() -> ManualKillSwitchState:
        return ManualKillSwitchState(
            manual_blocked=True,
            updated_at=datetime(1970, 1, 1, tzinfo=timezone.utc),
            reason="manual_kill_switch_state_unavailable",
        )
