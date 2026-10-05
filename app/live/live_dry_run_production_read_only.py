from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from app.live.live_runtime_kill_switch_composition import LiveRuntimeKillSwitchComposition
from app.live.live_runtime_read_only_composition import (
    LiveRuntimeReadOnlyProviderFactory,
    LiveRuntimeReadOnlyProviders,
)
from app.live.live_runtime_safety_state import LiveRuntimeSafetyStateProvider
from app.runtime.daily_report_service import SQLiteDailyTradeRepository
from app.runtime.session_service import RuntimeSessionService

NowProvider = Callable[[], datetime]


@dataclass(frozen=True, slots=True)
class ProductionReadOnlyPaths:
    paper_database_path: Path = Path("data/katana.db")
    runtime_status_path: Path = Path("reports/service/paper_trading_runtime_status.json")
    kabu_station_report_path: Path = Path("reports/live/kabu_station_read_only.json")
    three_way_reconciliation_report_path: Path = Path("reports/live/three_way_reconciliation.json")
    fault_tolerance_state_path: Path = Path("reports/live/fault_tolerance_state.json")
    manual_kill_switch_state_path: Path = Path("reports/live/manual_kill_switch_state.json")


class SavedPaperRuntimeStatusProvider:
    """Read the already-published Paper runtime status without touching runtime state."""

    def __init__(
        self,
        path: Path,
        *,
        stale_after_seconds: float = 180.0,
        now_provider: NowProvider | None = None,
    ) -> None:
        if stale_after_seconds <= 0:
            raise ValueError("stale_after_seconds must be greater than zero.")
        self.path = Path(path)
        self.stale_after_seconds = float(stale_after_seconds)
        self.now_provider = now_provider or (lambda: datetime.now(timezone.utc))

    def runtime_health_ok(self) -> bool:
        payload = self._read()
        if payload is None:
            return False
        return (
            payload.get("available") is True
            and str(payload.get("state", "")).strip().lower() == "running"
            and self._fresh(payload)
            and not payload.get("error_message")
        )

    def heartbeat_alive(self) -> bool:
        payload = self._read()
        if payload is None:
            return False
        return (
            payload.get("available") is True
            and str(payload.get("state", "")).strip().lower() == "running"
            and self._fresh(payload)
        )

    def _fresh(self, payload: dict) -> bool:
        raw = payload.get("generated_at")
        if not isinstance(raw, str) or not raw.strip():
            return False
        try:
            generated_at = datetime.fromisoformat(raw)
        except ValueError:
            return False
        if generated_at.tzinfo is None:
            return False
        now = self.now_provider()
        if now.tzinfo is None:
            raise ValueError("now_provider must return a timezone-aware datetime.")
        age = (
            now.astimezone(timezone.utc)
            - generated_at.astimezone(timezone.utc)
        ).total_seconds()
        return 0.0 <= age < self.stale_after_seconds

    def _read(self) -> dict | None:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return None
        return payload if isinstance(payload, dict) else None


@dataclass(frozen=True, slots=True)
class ProductionDryRunReadOnlyBundle:
    providers: LiveRuntimeReadOnlyProviders
    safety_snapshot_provider: LiveRuntimeSafetyStateProvider
    kill_switch_snapshot_provider: LiveRuntimeKillSwitchComposition


class ProductionDryRunReadOnlyFactory:
    """Build standalone, saved-state-only inputs for the operator dry-run."""

    @staticmethod
    def create(
        *,
        paths: ProductionReadOnlyPaths | None = None,
        max_daily_loss: float = 50_000.0,
        max_consecutive_losses: int = 3,
        runtime_stale_after_seconds: float = 180.0,
        broker_maximum_age_seconds: float = 120.0,
        now_provider: NowProvider | None = None,
    ) -> ProductionDryRunReadOnlyBundle:
        resolved = paths or ProductionReadOnlyPaths()

        # RuntimeSessionService is supplied only because the existing read-only
        # factory owns the saved broker/portfolio/reconciliation/manual readers.
        # Its in-memory runtime providers are replaced immediately below and are
        # never evaluated by this standalone composition.
        base = LiveRuntimeReadOnlyProviderFactory.create(
            daily_trade_repository=SQLiteDailyTradeRepository(
                resolved.paper_database_path
            ),
            runtime_session_service=RuntimeSessionService(
                now_provider=now_provider
            ),
            kabu_station_report_path=resolved.kabu_station_report_path,
            three_way_reconciliation_report_path=(
                resolved.three_way_reconciliation_report_path
            ),
            fault_tolerance_state_path=resolved.fault_tolerance_state_path,
            manual_kill_switch_state_path=resolved.manual_kill_switch_state_path,
            heartbeat_stale_after_seconds=runtime_stale_after_seconds,
            broker_maximum_age_seconds=broker_maximum_age_seconds,
            now_provider=now_provider,
        )

        saved_runtime = SavedPaperRuntimeStatusProvider(
            resolved.runtime_status_path,
            stale_after_seconds=runtime_stale_after_seconds,
            now_provider=now_provider,
        )
        providers = replace(
            base,
            runtime_health_ok_provider=saved_runtime.runtime_health_ok,
            heartbeat_alive_provider=saved_runtime.heartbeat_alive,
        )

        safety = LiveRuntimeSafetyStateProvider(
            reconciliation_report_provider=providers.reconciliation_report_provider,
            fault_tolerance_attempt_provider=providers.fault_tolerance_attempt_provider,
            now_provider=now_provider,
        )
        kill_switch = LiveRuntimeKillSwitchComposition(
            daily_profit_loss_provider=providers.daily_profit_loss_provider,
            consecutive_loss_count_provider=providers.consecutive_loss_count_provider,
            runtime_health_ok_provider=providers.runtime_health_ok_provider,
            heartbeat_alive_provider=providers.heartbeat_alive_provider,
            broker_available_provider=providers.broker_available_provider,
            manual_blocked_provider=providers.manual_blocked_provider,
            max_daily_loss=max_daily_loss,
            max_consecutive_losses=max_consecutive_losses,
            now_provider=now_provider,
        )
        return ProductionDryRunReadOnlyBundle(
            providers=providers,
            safety_snapshot_provider=safety,
            kill_switch_snapshot_provider=kill_switch,
        )
