"""Persistent read-only-derived peak equity state for future live risk checks."""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from collections.abc import Callable


NowProvider = Callable[[], datetime]


@dataclass(frozen=True, slots=True)
class LiveEquityPeakState:
    """Highest observed live-account equity and its update time."""

    peak_equity: float
    updated_at: datetime

    def __post_init__(self) -> None:
        if not math.isfinite(self.peak_equity) or self.peak_equity < 0:
            raise ValueError("peak_equity must be finite and non-negative.")
        if self.updated_at.tzinfo is None:
            raise ValueError("updated_at must be timezone-aware.")


class LiveEquityPeakStore:
    """Atomically persist the highest observed live-account equity.

    The store never accesses a broker or network.  Callers may update it only
    with equity already derived from a saved/read-only live broker snapshot.
    """

    def __init__(
        self,
        path: Path,
        *,
        now_provider: NowProvider | None = None,
    ) -> None:
        self.path = Path(path)
        self.now_provider = now_provider or (
            lambda: datetime.now(timezone.utc)
        )

    def read(self) -> LiveEquityPeakState:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise RuntimeError(
                "Live equity peak state is unavailable or invalid."
            ) from error

        if not isinstance(raw, dict):
            raise RuntimeError("Live equity peak state root must be an object.")

        try:
            peak = float(raw["peak_equity"])
            updated_at = datetime.fromisoformat(str(raw["updated_at"]))
        except (KeyError, TypeError, ValueError) as error:
            raise RuntimeError(
                "Live equity peak state fields are invalid."
            ) from error

        try:
            return LiveEquityPeakState(
                peak_equity=peak,
                updated_at=updated_at,
            )
        except ValueError as error:
            raise RuntimeError(
                "Live equity peak state values are invalid."
            ) from error

    def peak_equity(self) -> float:
        """Return the persisted peak or fail closed if it is unavailable."""
        return self.read().peak_equity

    def observe(self, current_equity: float) -> LiveEquityPeakState:
        """Persist max(previous peak, current equity) using an atomic replace."""
        equity = self._validate_equity(current_equity)
        now = self.now_provider()
        if now.tzinfo is None:
            raise RuntimeError("now_provider must return timezone-aware datetime.")

        try:
            previous = self.read()
        except RuntimeError:
            if self.path.exists():
                raise
            peak = equity
        else:
            peak = max(previous.peak_equity, equity)

        state = LiveEquityPeakState(
            peak_equity=peak,
            updated_at=now.astimezone(timezone.utc),
        )
        self._write(state)
        return state

    def _write(self, state: LiveEquityPeakState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(
            f".{self.path.name}.{os.getpid()}.tmp"
        )
        payload = {
            "peak_equity": state.peak_equity,
            "updated_at": state.updated_at.isoformat(),
        }
        try:
            temporary.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            os.replace(temporary, self.path)
        finally:
            if temporary.exists():
                temporary.unlink()

    @staticmethod
    def _validate_equity(value: object) -> float:
        if isinstance(value, bool):
            raise RuntimeError("Live equity must be numeric.")
        try:
            equity = float(value)
        except (TypeError, ValueError) as error:
            raise RuntimeError("Live equity must be numeric.") from error
        if not math.isfinite(equity) or equity < 0:
            raise RuntimeError(
                "Live equity must be finite and non-negative."
            )
        return equity
