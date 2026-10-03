"""Read-only bridges from existing runtime/broker state to live safety inputs."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Protocol

from app.live.kabu_station_read_only import KabuStationReadOnlySnapshot
from app.runtime.runtime_health_monitor_models import RuntimeActivitySnapshot, RuntimeHealthStatus
from app.runtime.runtime_health_monitor_service import RuntimeHealthMonitorService
from app.runtime.session_models import RuntimeSessionSnapshot
from app.runtime.session_service import RuntimeSessionService

NowProvider = Callable[[], datetime]


class KabuStationReadOnlySnapshotProvider(Protocol):
    def __call__(self) -> KabuStationReadOnlySnapshot | None: ...


class RuntimeSessionActivityProvider:
    """Convert existing RuntimeSessionService state into health-monitor input."""

    def __init__(self, *, session_service: RuntimeSessionService, now_provider: NowProvider | None = None) -> None:
        self.session_service = session_service
        self.now_provider = now_provider or (lambda: datetime.now(timezone.utc))

    def __call__(self) -> RuntimeActivitySnapshot:
        return self.from_session_snapshot(
            snapshot=self.session_service.snapshot(),
            checked_at=self._now(),
        )

    @staticmethod
    def from_session_snapshot(*, snapshot: RuntimeSessionSnapshot, checked_at: datetime) -> RuntimeActivitySnapshot:
        if checked_at.tzinfo is None:
            raise ValueError("checked_at must be timezone-aware.")
        return RuntimeActivitySnapshot(
            checked_at=checked_at.astimezone(timezone.utc),
            running=snapshot.is_running,
            started_at=snapshot.started_at,
            last_heartbeat_at=snapshot.last_heartbeat_at,
            last_cycle_at=snapshot.last_cycle_at,
        )

    def _now(self) -> datetime:
        current = self.now_provider()
        if current.tzinfo is None:
            raise ValueError("now_provider must return a timezone-aware datetime.")
        return current.astimezone(timezone.utc)


class RuntimeHealthOkProvider:
    """Evaluate current runtime activity without mutating runtime state."""

    def __init__(self, *, activity_provider: Callable[[], RuntimeActivitySnapshot], monitor: RuntimeHealthMonitorService | None = None) -> None:
        self.activity_provider = activity_provider
        self.monitor = monitor or RuntimeHealthMonitorService()

    def __call__(self) -> bool:
        report = self.monitor.evaluate(self.activity_provider())
        return report.status is RuntimeHealthStatus.HEALTHY


class RuntimeSessionHeartbeatAliveProvider:
    """Read RuntimeSession heartbeat freshness without recording a heartbeat."""

    def __init__(self, *, session_service: RuntimeSessionService, stale_after_seconds: float = 180.0, now_provider: NowProvider | None = None) -> None:
        if stale_after_seconds <= 0:
            raise ValueError("stale_after_seconds must be greater than zero.")
        self.session_service = session_service
        self.stale_after_seconds = float(stale_after_seconds)
        self.now_provider = now_provider or (lambda: datetime.now(timezone.utc))

    def __call__(self) -> bool:
        current = self._now()
        snapshot = self.session_service.snapshot()
        if not snapshot.is_running or snapshot.last_heartbeat_at is None:
            return False
        heartbeat = snapshot.last_heartbeat_at
        if heartbeat.tzinfo is None:
            return False
        age = (current - heartbeat.astimezone(timezone.utc)).total_seconds()
        return 0.0 <= age < self.stale_after_seconds

    def _now(self) -> datetime:
        current = self.now_provider()
        if current.tzinfo is None:
            raise ValueError("now_provider must return a timezone-aware datetime.")
        return current.astimezone(timezone.utc)


class KabuStationBrokerAvailabilityProvider:
    """Map an already-collected read-only broker snapshot to availability."""

    def __init__(self, *, snapshot_provider: KabuStationReadOnlySnapshotProvider, maximum_age_seconds: float = 120.0, maximum_future_skew_seconds: float = 5.0, now_provider: NowProvider | None = None) -> None:
        if maximum_age_seconds <= 0:
            raise ValueError("maximum_age_seconds must be greater than zero.")
        if maximum_future_skew_seconds < 0:
            raise ValueError("maximum_future_skew_seconds must not be negative.")
        self.snapshot_provider = snapshot_provider
        self.maximum_age_seconds = float(maximum_age_seconds)
        self.maximum_future_skew_seconds = float(maximum_future_skew_seconds)
        self.now_provider = now_provider or (lambda: datetime.now(timezone.utc))

    def __call__(self) -> bool:
        try:
            snapshot = self.snapshot_provider()
        except Exception:
            return False
        if snapshot is None or snapshot.generated_at.tzinfo is None:
            return False
        current = self._now()
        generated_at = snapshot.generated_at.astimezone(timezone.utc)
        age = (current - generated_at).total_seconds()
        if age < -self.maximum_future_skew_seconds or age > self.maximum_age_seconds:
            return False
        return (
            snapshot.connected
            and snapshot.token_issued
            and snapshot.state.strip().lower() == "complete"
            and not snapshot.errors
        )

    def _now(self) -> datetime:
        current = self.now_provider()
        if current.tzinfo is None:
            raise ValueError("now_provider must return a timezone-aware datetime.")
        return current.astimezone(timezone.utc)
