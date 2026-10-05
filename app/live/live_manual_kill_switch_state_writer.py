"""Atomic writer for operator-controlled manual Kill Switch state."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from app.live.live_manual_kill_switch_state import (
    MANUAL_KILL_SWITCH_SCHEMA_VERSION,
    ManualKillSwitchState,
)


NowProvider = Callable[[], datetime]


class ManualKillSwitchStateWriter:
    """Persist explicit engage/release commands atomically."""

    def __init__(
        self,
        path: Path,
        *,
        now_provider: NowProvider | None = None,
    ) -> None:
        self.path = Path(path)
        self.now_provider = (
            now_provider
            if now_provider is not None
            else lambda: datetime.now(timezone.utc)
        )

    def engage(self, *, reason: str = "manual_operator_stop") -> ManualKillSwitchState:
        return self._write(manual_blocked=True, reason=reason)

    def release(
        self,
        *,
        reason: str = "manual_operator_release",
    ) -> ManualKillSwitchState:
        return self._write(manual_blocked=False, reason=reason)

    def _write(
        self,
        *,
        manual_blocked: bool,
        reason: str,
    ) -> ManualKillSwitchState:
        state = ManualKillSwitchState(
            manual_blocked=manual_blocked,
            updated_at=self._current_time(),
            reason=reason,
        )
        payload = {
            "schema_version": MANUAL_KILL_SWITCH_SCHEMA_VERSION,
            "manual_blocked": state.manual_blocked,
            "updated_at": state.updated_at.isoformat(),
            "reason": state.reason,
        }

        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.path.with_name(f".{self.path.name}.tmp")
        try:
            temporary_path.write_text(
                json.dumps(
                    payload,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                encoding="utf-8",
            )
            os.replace(temporary_path, self.path)
        finally:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
        return state

    def _current_time(self) -> datetime:
        current = self.now_provider()
        if current.tzinfo is None:
            raise ValueError("now_provider must return a timezone-aware datetime.")
        return current.astimezone(timezone.utc)
