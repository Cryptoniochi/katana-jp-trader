"""Atomic persistence for the latest fault-tolerance safety state."""

from __future__ import annotations

import json
import os
from pathlib import Path
from uuid import uuid4

from app.live.live_fault_tolerance_saved_state import SavedFaultToleranceState
from app.supervisor.fault_tolerance_models import FaultToleranceAttempt


class FaultToleranceSavedStateWriter:
    """Persist the latest completed fault-tolerance attempt atomically."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def write_attempt(
        self,
        attempt: FaultToleranceAttempt,
    ) -> SavedFaultToleranceState:
        if not isinstance(attempt, FaultToleranceAttempt):
            raise TypeError("attempt must be a FaultToleranceAttempt")

        state = SavedFaultToleranceState(
            attempt_number=attempt.attempt_number,
            checked_at=attempt.checked_at,
            decision=attempt.decision,
            consecutive_failure_count=attempt.consecutive_failure_count,
            message=attempt.message,
        )
        self.write(state)
        return state

    def write(self, state: SavedFaultToleranceState) -> None:
        if not isinstance(state, SavedFaultToleranceState):
            raise TypeError("state must be a SavedFaultToleranceState")

        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "attempt_number": state.attempt_number,
            "checked_at": state.checked_at.isoformat(),
            "decision": state.decision.value,
            "consecutive_failure_count": state.consecutive_failure_count,
            "message": state.message,
        }

        temporary_path = self.path.with_name(
            f".{self.path.name}.{uuid4().hex}.tmp"
        )
        try:
            with temporary_path.open("x", encoding="utf-8", newline="\n") as handle:
                json.dump(
                    payload,
                    handle,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, self.path)
        finally:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass
