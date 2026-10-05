"""Read-only production safety diagnostics for Phase 6-D Step 6C-E."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.live.live_broker_transport import LIVE_BROKER_TRANSPORT_ENABLED
from app.live.live_order_adapter import LIVE_ORDER_TRANSMISSION_ENABLED
from app.live.locked_live_runtime_integration import LOCKED_LIVE_RUNTIME_INTEGRATION_ENABLED


@dataclass(frozen=True, slots=True)
class SafetyDiagnosticItem:
    key: str
    passed: bool
    message: str


@dataclass(frozen=True, slots=True)
class ProductionSafetyDiagnosticReport:
    generated_at: datetime
    items: tuple[SafetyDiagnosticItem, ...]
    activation_inputs_ready: bool
    transport_ready: bool = False
    live_order_ready: bool = False

    def __post_init__(self) -> None:
        if self.generated_at.tzinfo is None:
            raise ValueError("generated_at must be timezone-aware.")
        if self.transport_ready or self.live_order_ready:
            raise ValueError("Phase 6-D transport/live order readiness must remain False.")


@dataclass(frozen=True, slots=True)
class ProductionSafetyDiagnosticPaths:
    runtime_status: Path = Path("reports/service/paper_trading_runtime_status.json")
    kabu_station: Path = Path("reports/live/kabu_station_read_only.json")
    reconciliation: Path = Path("reports/live/three_way_reconciliation.json")
    fault_tolerance: Path = Path("reports/live/fault_tolerance_state.json")
    manual_kill_switch: Path = Path("reports/live/manual_kill_switch_state.json")


class ProductionSafetyDiagnostic:
    """Inspect saved production safety evidence without changing it."""

    def __init__(
        self,
        *,
        paths: ProductionSafetyDiagnosticPaths | None = None,
        now_provider=None,
        runtime_maximum_age: timedelta = timedelta(minutes=3),
        broker_maximum_age: timedelta = timedelta(minutes=3),
        reconciliation_maximum_age: timedelta = timedelta(minutes=2),
        fault_tolerance_maximum_age: timedelta = timedelta(minutes=3),
    ) -> None:
        self.paths = paths or ProductionSafetyDiagnosticPaths()
        self.now_provider = now_provider or (lambda: datetime.now(timezone.utc))
        self.runtime_maximum_age = runtime_maximum_age
        self.broker_maximum_age = broker_maximum_age
        self.reconciliation_maximum_age = reconciliation_maximum_age
        self.fault_tolerance_maximum_age = fault_tolerance_maximum_age

    def check(self) -> ProductionSafetyDiagnosticReport:
        now = self._now()
        items = (
            self._runtime(now),
            self._broker(now),
            self._reconciliation(now),
            self._fault_tolerance(now),
            self._manual_kill_switch(),
            self._hard_lock("locked_live_runtime_integration", LOCKED_LIVE_RUNTIME_INTEGRATION_ENABLED),
            self._hard_lock("live_broker_transport", LIVE_BROKER_TRANSPORT_ENABLED),
            self._hard_lock("live_order_transmission", LIVE_ORDER_TRANSMISSION_ENABLED),
        )
        return ProductionSafetyDiagnosticReport(
            generated_at=now,
            items=items,
            activation_inputs_ready=all(item.passed for item in items[:5]),
            transport_ready=False,
            live_order_ready=False,
        )

    def _runtime(self, now: datetime) -> SafetyDiagnosticItem:
        payload, error = self._load_json(self.paths.runtime_status)
        if error:
            return self._blocked("paper_runtime", error)
        if payload.get("available") is not True:
            return self._blocked("paper_runtime", "runtime status is unavailable")
        state = str(payload.get("state", "")).strip().lower()
        if state != "running":
            return self._blocked("paper_runtime", f"runtime state={state or 'missing'}")
        return self._fresh_item("paper_runtime", payload.get("generated_at"), now, self.runtime_maximum_age, "runtime is running and fresh")

    def _broker(self, now: datetime) -> SafetyDiagnosticItem:
        payload, error = self._load_json(self.paths.kabu_station)
        if error:
            return self._blocked("kabu_station", error)
        if payload.get("connected") is not True:
            return self._blocked("kabu_station", "saved broker snapshot is not connected")
        return self._fresh_item("kabu_station", payload.get("generated_at"), now, self.broker_maximum_age, "saved broker snapshot is connected and fresh")

    def _reconciliation(self, now: datetime) -> SafetyDiagnosticItem:
        payload, error = self._load_json(self.paths.reconciliation)
        if error:
            return self._blocked("reconciliation", error)
        fresh = self._fresh_item("reconciliation", payload.get("generated_at"), now, self.reconciliation_maximum_age, "reconciliation is fresh")
        if not fresh.passed:
            return fresh
        if payload.get("consistent") is not True:
            return self._blocked("reconciliation", f"reconciliation is not consistent; state={payload.get('state', 'unknown')}")
        return SafetyDiagnosticItem("reconciliation", True, "reconciliation is consistent and fresh")

    def _fault_tolerance(self, now: datetime) -> SafetyDiagnosticItem:
        payload, error = self._load_json(self.paths.fault_tolerance)
        if error:
            return self._blocked("fault_tolerance", error)
        fresh = self._fresh_item("fault_tolerance", payload.get("checked_at"), now, self.fault_tolerance_maximum_age, "fault-tolerance state is fresh")
        if not fresh.passed:
            return fresh
        decision = str(payload.get("decision", "")).strip().lower()
        if decision == "safe_stop":
            return self._blocked("fault_tolerance", "saved decision=SAFE_STOP")
        if not decision:
            return self._blocked("fault_tolerance", "saved decision is missing")
        return SafetyDiagnosticItem("fault_tolerance", True, f"saved decision={decision}")

    def _manual_kill_switch(self) -> SafetyDiagnosticItem:
        payload, error = self._load_json(self.paths.manual_kill_switch)
        if error:
            return self._blocked("manual_kill_switch", error)
        if payload.get("manual_blocked") is not False:
            return self._blocked("manual_kill_switch", "manual kill switch is BLOCKED")
        reason = str(payload.get("reason", "")).strip()
        return SafetyDiagnosticItem("manual_kill_switch", True, "manual kill switch is RELEASED" + (f"; reason={reason}" if reason else ""))

    @staticmethod
    def _hard_lock(key: str, enabled: bool) -> SafetyDiagnosticItem:
        if enabled:
            return SafetyDiagnosticItem(key, False, "UNSAFE: Phase 6-D hard lock is enabled")
        return SafetyDiagnosticItem(key, True, "safe: Phase 6-D hard lock remains disabled")

    def _fresh_item(self, key: str, raw_timestamp: Any, now: datetime, maximum_age: timedelta, ready_message: str) -> SafetyDiagnosticItem:
        try:
            timestamp = self._timestamp(raw_timestamp)
        except Exception as error:
            return self._blocked(key, f"invalid timestamp: {type(error).__name__}: {error}")
        age = now - timestamp
        if age < timedelta(0):
            return self._blocked(key, "saved timestamp is in the future")
        if age > maximum_age:
            return self._blocked(key, f"saved state is stale; age_seconds={age.total_seconds():.1f}")
        return SafetyDiagnosticItem(key, True, ready_message)

    @staticmethod
    def _load_json(path: Path) -> tuple[dict[str, Any], str | None]:
        try:
            text = Path(path).read_text(encoding="utf-8")
        except FileNotFoundError:
            return {}, f"state file is missing: {path}"
        except Exception as error:
            return {}, f"state file unavailable: {type(error).__name__}: {error}"
        try:
            payload = json.loads(text)
        except Exception as error:
            return {}, f"invalid JSON: {type(error).__name__}: {error}"
        if not isinstance(payload, dict):
            return {}, "JSON root must be an object"
        return payload, None

    @staticmethod
    def _timestamp(value: Any) -> datetime:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("timestamp is missing")
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")
        return parsed.astimezone(timezone.utc)

    def _now(self) -> datetime:
        current = self.now_provider()
        if current.tzinfo is None:
            raise ValueError("now_provider must return a timezone-aware datetime.")
        return current.astimezone(timezone.utc)

    @staticmethod
    def _blocked(key: str, message: str) -> SafetyDiagnosticItem:
        return SafetyDiagnosticItem(key, False, message)
