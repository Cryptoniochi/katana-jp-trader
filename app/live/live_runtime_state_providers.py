"""Read-only providers for real runtime safety state used by locked live execution.

Phase 6-C Step 4C-4A deliberately only reads existing state.  It does not
start services, mutate runtime state, fabricate healthy values, construct live
execution components, or perform broker/network I/O.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path
from typing import Protocol

from app.live.three_way_reconciliation import (
    OrderMismatch,
    ReconciliationOrder,
    ThreeWayReconciliationReport,
)
from app.runtime.runtime_heartbeat_models import RuntimeHeartbeatSnapshot
from app.runtime.runtime_heartbeat_service import RuntimeHeartbeatService
from app.supervisor.fault_tolerance_models import FaultToleranceAttempt


class FaultToleranceHistorySource(Protocol):
    """Minimal read-only surface exposed by FaultToleranceService."""

    def history(self) -> tuple[FaultToleranceAttempt, ...]: ...


class ThreeWayReconciliationReportReader:
    """Read the atomic Phase 5B reconciliation JSON without changing it."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def read(self) -> ThreeWayReconciliationReport | None:
        if not self.path.exists():
            return None

        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Three-way reconciliation report must be a JSON object.")

        mismatches_payload = payload.get("mismatches") or []
        if not isinstance(mismatches_payload, list):
            raise ValueError("Three-way reconciliation mismatches must be a list.")

        return ThreeWayReconciliationReport(
            generated_at=self._datetime(payload, "generated_at"),
            trading_date=self._date(payload, "trading_date"),
            state=self._string(payload, "state"),
            consistent=self._boolean(payload, "consistent"),
            paper_order_count=self._integer(payload, "paper_order_count"),
            shadow_order_count=self._integer(payload, "shadow_order_count"),
            matched_order_count=self._integer(payload, "matched_order_count"),
            paper_only_order_ids=self._string_tuple(payload, "paper_only_order_ids"),
            shadow_only_order_ids=self._string_tuple(payload, "shadow_only_order_ids"),
            mismatches=tuple(self._mismatch(item) for item in mismatches_payload),
            broker_snapshot_connected=self._boolean(payload, "broker_snapshot_connected"),
            broker_active_order_count=self._integer(payload, "broker_active_order_count"),
            broker_position_count=self._integer(payload, "broker_position_count"),
            broker_active_order_ids=self._string_tuple(payload, "broker_active_order_ids"),
            broker_position_codes=self._string_tuple(payload, "broker_position_codes"),
            live_order_ready=self._boolean(payload, "live_order_ready"),
            message=self._string(payload, "message"),
        )

    @staticmethod
    def _mismatch(value: object) -> OrderMismatch:
        if not isinstance(value, dict):
            raise ValueError("Three-way reconciliation mismatch must be an object.")
        return OrderMismatch(
            order_id=ThreeWayReconciliationReportReader._string(value, "order_id"),
            paper=ThreeWayReconciliationReportReader._order(value.get("paper")),
            shadow=ThreeWayReconciliationReportReader._order(value.get("shadow")),
        )

    @staticmethod
    def _order(value: object) -> ReconciliationOrder:
        if not isinstance(value, dict):
            raise ValueError("Three-way reconciliation order must be an object.")
        return ReconciliationOrder(
            order_id=ThreeWayReconciliationReportReader._string(value, "order_id"),
            signal_id=ThreeWayReconciliationReportReader._string(value, "signal_id"),
            code=ThreeWayReconciliationReportReader._string(value, "code"),
            side=ThreeWayReconciliationReportReader._string(value, "side"),
            quantity=ThreeWayReconciliationReportReader._integer(value, "quantity"),
        )

    @staticmethod
    def _datetime(payload: dict[str, object], key: str) -> datetime:
        value = ThreeWayReconciliationReportReader._string(payload, key)
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.tzinfo is None:
            raise ValueError(f"{key} must be timezone-aware.")
        return result

    @staticmethod
    def _date(payload: dict[str, object], key: str) -> date:
        return date.fromisoformat(ThreeWayReconciliationReportReader._string(payload, key))

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
    def _integer(payload: dict[str, object], key: str) -> int:
        value = payload.get(key)
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{key} must be an integer.")
        if value < 0:
            raise ValueError(f"{key} must not be negative.")
        return value

    @staticmethod
    def _string_tuple(payload: dict[str, object], key: str) -> tuple[str, ...]:
        value = payload.get(key)
        if not isinstance(value, list):
            raise ValueError(f"{key} must be a list.")
        if not all(isinstance(item, str) and item.strip() for item in value):
            raise ValueError(f"{key} must contain only non-empty strings.")
        return tuple(item.strip() for item in value)


class LatestFaultToleranceAttemptProvider:
    """Expose the latest already-recorded fault-tolerance attempt."""

    def __init__(self, source: FaultToleranceHistorySource) -> None:
        self.source = source

    def __call__(self) -> FaultToleranceAttempt | None:
        history = self.source.history()
        return history[-1] if history else None


class RuntimeHeartbeatSnapshotProvider:
    """Evaluate the existing heartbeat service without recording a heartbeat."""

    def __init__(
        self,
        service: RuntimeHeartbeatService,
        *,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self.service = service
        self.now_provider = now_provider

    def __call__(self) -> RuntimeHeartbeatSnapshot:
        if self.now_provider is None:
            return self.service.snapshot()
        return self.service.snapshot(checked_at=self.now_provider())
