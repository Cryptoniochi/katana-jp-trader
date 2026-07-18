"""RuntimeHealthMonitorServiceのテスト。"""

from datetime import datetime, timedelta, timezone

from app.runtime.runtime_health_monitor_models import (
    RuntimeActivitySnapshot,
    RuntimeHealthMonitorPolicy,
    RuntimeHealthStatus,
)
from app.runtime.runtime_health_monitor_service import (
    RuntimeHealthMonitorService,
)


NOW = datetime(
    2026,
    7,
    18,
    0,
    10,
    tzinfo=timezone.utc,
)


def snapshot(
    *,
    running: bool = True,
    heartbeat_age: float | None = 10.0,
    cycle_age: float | None = 20.0,
) -> RuntimeActivitySnapshot:
    return RuntimeActivitySnapshot(
        checked_at=NOW,
        running=running,
        started_at=(
            NOW - timedelta(hours=1)
            if running
            else None
        ),
        last_heartbeat_at=(
            None
            if heartbeat_age is None
            else NOW - timedelta(seconds=heartbeat_age)
        ),
        last_cycle_at=(
            None
            if cycle_age is None
            else NOW - timedelta(seconds=cycle_age)
        ),
    )


def service() -> RuntimeHealthMonitorService:
    return RuntimeHealthMonitorService(
        policy=RuntimeHealthMonitorPolicy(
            heartbeat_warning_seconds=90.0,
            heartbeat_critical_seconds=180.0,
            cycle_warning_seconds=180.0,
            cycle_critical_seconds=300.0,
        )
    )


def test_healthy_activity() -> None:
    report = service().evaluate(snapshot())

    assert report.status is RuntimeHealthStatus.HEALTHY
    assert report.requires_attention is False
    assert report.reasons == ()


def test_idle_before_first_activity() -> None:
    report = service().evaluate(
        snapshot(
            heartbeat_age=None,
            cycle_age=None,
        )
    )

    assert report.status is RuntimeHealthStatus.IDLE
    assert report.requires_attention is False


def test_warning_for_stale_heartbeat() -> None:
    report = service().evaluate(
        snapshot(
            heartbeat_age=100.0,
            cycle_age=30.0,
        )
    )

    assert report.status is RuntimeHealthStatus.WARNING
    assert "Heartbeat" in report.reasons[0]


def test_critical_for_stale_cycle() -> None:
    report = service().evaluate(
        snapshot(
            heartbeat_age=20.0,
            cycle_age=350.0,
        )
    )

    assert report.status is RuntimeHealthStatus.CRITICAL
    assert any(
        "Trading Cycle" in reason
        for reason in report.reasons
    )


def test_stopped_runtime() -> None:
    report = service().evaluate(
        snapshot(
            running=False,
            heartbeat_age=None,
            cycle_age=None,
        )
    )

    assert report.status is RuntimeHealthStatus.STOPPED
    assert report.requires_attention is True
