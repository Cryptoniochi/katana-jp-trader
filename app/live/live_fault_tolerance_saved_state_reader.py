"""Strict read-only reader for saved fault-tolerance safety state."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from app.live.live_fault_tolerance_saved_state import SavedFaultToleranceState
from app.supervisor.fault_tolerance_models import (
    FaultToleranceAttempt,
    FaultToleranceDecision,
)


class FaultToleranceSavedStateReader:
    """Read the latest durable state without performing recovery or network I/O."""

    _REQUIRED_KEYS = {
        "attempt_number",
        "checked_at",
        "decision",
        "consecutive_failure_count",
        "message",
    }

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def read_state(self) -> SavedFaultToleranceState | None:
        if not self.path.exists():
            return None

        with self.path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)

        if not isinstance(payload, dict):
            raise ValueError("fault-tolerance state must be a JSON object")
        if set(payload) != self._REQUIRED_KEYS:
            raise ValueError("fault-tolerance state has an invalid schema")

        checked_at_raw = payload["checked_at"]
        if not isinstance(checked_at_raw, str):
            raise ValueError("checked_at must be an ISO 8601 string")

        try:
            checked_at = datetime.fromisoformat(checked_at_raw)
            decision = FaultToleranceDecision(payload["decision"])
        except (TypeError, ValueError) as error:
            raise ValueError("fault-tolerance state contains invalid values") from error

        return SavedFaultToleranceState(
            attempt_number=self._strict_int(
                payload["attempt_number"],
                name="attempt_number",
            ),
            checked_at=checked_at,
            decision=decision,
            consecutive_failure_count=self._strict_int(
                payload["consecutive_failure_count"],
                name="consecutive_failure_count",
            ),
            message=self._strict_string(payload["message"], name="message"),
        )

    def read_attempt(self) -> FaultToleranceAttempt | None:
        """Expose only the safety fields consumed by live safety.

        Supervisor and recovery details are deliberately not reconstructed from
        durable state.  The live safety layer only needs checked_at and decision,
        so a lightweight compatible object is returned by `__call__` instead.
        """
        raise NotImplementedError(
            "full FaultToleranceAttempt reconstruction is intentionally unsupported"
        )

    def __call__(self):
        state = self.read_state()
        if state is None:
            return None
        return SavedFaultToleranceAttemptView(
            checked_at=state.checked_at,
            decision=state.decision,
        )

    @staticmethod
    def _strict_int(value: object, *, name: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{name} must be an integer")
        return value

    @staticmethod
    def _strict_string(value: object, *, name: str) -> str:
        if not isinstance(value, str):
            raise ValueError(f"{name} must be a string")
        return value


class SavedFaultToleranceAttemptView:
    """Minimal protocol-compatible view consumed by LiveRuntimeSafetyStateProvider."""

    __slots__ = ("checked_at", "decision")

    def __init__(
        self,
        *,
        checked_at: datetime,
        decision: FaultToleranceDecision,
    ) -> None:
        self.checked_at = checked_at
        self.decision = decision
