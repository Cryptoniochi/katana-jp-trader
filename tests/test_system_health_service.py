"""SystemHealthServiceのテスト。"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.monitoring.runtime_metrics import (
    RuntimeMetricName,
    RuntimeMetricsSnapshot,
)
from app.monitoring.system_health_models import (
    SystemHealthPolicy,
    SystemHealthStatus,
)
from app.monitoring.system_health_service import (
    SystemHealthService,
)
from app.monitoring.update_health_service import (
    UpdateHealthReport,
    UpdateHealthStatus,
)


NOW = datetime(
    2026,
    7,
    17,
    6,
    0,
    tzinfo=timezone.utc,
)


def update_report(
    status: UpdateHealthStatus = UpdateHealthStatus.HEALTHY,
) -> UpdateHealthReport:
    return UpdateHealthReport(
        status=status,
        checked_at=NOW,
        reason=f"update {status.value}",
        latest_run=None,
        latest_success=None,
        consecutive_failure_count=0,
        seconds_since_latest_run=None,
        seconds_since_latest_success=None,
    )


def runtime_snapshot(
    *,
    events: int = 100,
    errors: int = 0,
    delivered: int = 0,
    failed: int = 0,
) -> RuntimeMetricsSnapshot:
    return RuntimeMetricsSnapshot(
        generated_at=NOW,
        counts={
            RuntimeMetricName.DOMAIN_EVENT_COUNT: events,
            RuntimeMetricName.ERROR_OCCURRED_COUNT: errors,
            RuntimeMetricName.NOTIFICATION_DELIVERED_COUNT: delivered,
            RuntimeMetricName.NOTIFICATION_FAILED_COUNT: failed,
        },
    )


class FakeUpdateHealthService:
    def __init__(self, report: UpdateHealthReport) -> None:
        self.report = report

    def check(self) -> UpdateHealthReport:
        return self.report


class FakeRuntimeMetricsService:
    def __init__(
        self,
        snapshot: RuntimeMetricsSnapshot,
    ) -> None:
        self.current = snapshot

    def snapshot(self) -> RuntimeMetricsSnapshot:
        return self.current


def create_service(
    *,
    update: UpdateHealthReport | None = None,
    runtime: RuntimeMetricsSnapshot | None = None,
) -> SystemHealthService:
    return SystemHealthService(
        update_health_service=FakeUpdateHealthService(
            update or update_report()
        ),
        runtime_metrics_service=FakeRuntimeMetricsService(
            runtime or runtime_snapshot()
        ),
        policy=SystemHealthPolicy(
            warning_error_rate=0.05,
            critical_error_rate=0.20,
            warning_notification_failure_rate=0.10,
            critical_notification_failure_rate=0.50,
        ),
        now_provider=lambda: NOW,
    )


def test_healthy_when_all_sources_are_healthy() -> None:
    report = create_service().check()

    assert report.status is SystemHealthStatus.HEALTHY
    assert report.is_healthy
    assert report.reasons == ()


def test_update_warning_maps_to_warning() -> None:
    report = create_service(
        update=update_report(UpdateHealthStatus.WARNING)
    ).check()

    assert report.status is SystemHealthStatus.WARNING
    assert "自動更新基盤" in report.reasons[0]


def test_update_error_maps_to_critical() -> None:
    report = create_service(
        update=update_report(UpdateHealthStatus.ERROR)
    ).check()

    assert report.status is SystemHealthStatus.CRITICAL


def test_runtime_warning_error_rate() -> None:
    report = create_service(
        runtime=runtime_snapshot(
            events=100,
            errors=5,
        )
    ).check()

    assert report.status is SystemHealthStatus.WARNING


def test_runtime_critical_error_rate() -> None:
    report = create_service(
        runtime=runtime_snapshot(
            events=100,
            errors=20,
        )
    ).check()

    assert report.status is SystemHealthStatus.CRITICAL


def test_notification_failure_rate_maps_to_degraded() -> None:
    report = create_service(
        runtime=runtime_snapshot(
            delivered=1,
            failed=1,
        )
    ).check()

    assert report.status is SystemHealthStatus.DEGRADED


def test_highest_severity_wins() -> None:
    report = create_service(
        update=update_report(UpdateHealthStatus.WARNING),
        runtime=runtime_snapshot(
            events=10,
            errors=3,
        ),
    ).check()

    assert report.status is SystemHealthStatus.CRITICAL
    assert len(report.reasons) == 2


def test_policy_rejects_invalid_threshold_order() -> None:
    with pytest.raises(ValueError):
        SystemHealthPolicy(
            warning_error_rate=0.5,
            critical_error_rate=0.1,
        )


def test_service_rejects_naive_clock() -> None:
    service = SystemHealthService(
        update_health_service=FakeUpdateHealthService(
            update_report()
        ),
        runtime_metrics_service=FakeRuntimeMetricsService(
            runtime_snapshot()
        ),
        now_provider=lambda: datetime(2026, 7, 17),
    )

    with pytest.raises(
        ValueError,
        match="タイムゾーン",
    ):
        service.check()
