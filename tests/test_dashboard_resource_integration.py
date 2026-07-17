"""Runtime ResourceのDashboard統合テスト。"""

from datetime import datetime, timezone

from app.dashboard.dashboard_json import (
    dashboard_snapshot_to_dict,
)
from app.dashboard.dashboard_service import (
    DashboardService,
)
from app.runtime.resource_models import (
    RuntimeResourceSnapshot,
    RuntimeResourceThresholds,
)


NOW = datetime(
    2026,
    7,
    18,
    12,
    0,
    tzinfo=timezone.utc,
)


class ValueReader:
    def __init__(self, value) -> None:
        self.value = value

    def check(self):
        return self.value

    def snapshot(self):
        return self.value

    def create_snapshot(self, *, generated_at=None):
        return self.value

    def list_recent(self, **_kwargs):
        return []

    def summarize_date(self, _target_date):
        return self.value

    def get_dashboard_status(self):
        return self.value

    def latest(self):
        return self.value


class FailingResourceReader:
    def latest(self):
        raise RuntimeError("resource unavailable")


def resource_evaluation():
    return RuntimeResourceSnapshot(
        sampled_at=NOW,
        cpu_percent=95.0,
        rss_bytes=100,
        vms_bytes=200,
        thread_count=1,
        process_uptime_seconds=3600.0,
    ).evaluate(
        RuntimeResourceThresholds(
            cpu_warning_percent=50.0,
            cpu_critical_percent=90.0,
            rss_warning_bytes=1000,
            rss_critical_bytes=2000,
            thread_warning_count=10,
            thread_critical_count=20,
        )
    )


def create_service(resource_reader):
    none_reader = ValueReader(None)

    return DashboardService(
        system_health_reader=none_reader,
        runtime_metrics_reader=none_reader,
        portfolio_reader=none_reader,
        order_reader=none_reader,
        live_summary_reader=none_reader,
        broker_reader=none_reader,
        runtime_resource_reader=resource_reader,
        now_provider=lambda: NOW,
    )


def test_dashboard_service_reads_latest_resource() -> None:
    expected = resource_evaluation()
    snapshot = create_service(
        ValueReader(expected)
    ).create_snapshot()

    assert snapshot.runtime_resource == expected
    assert snapshot.is_complete


def test_dashboard_json_contains_runtime_resource() -> None:
    snapshot = create_service(
        ValueReader(resource_evaluation())
    ).create_snapshot()

    payload = dashboard_snapshot_to_dict(snapshot)

    assert payload["runtime_resource"]["status"] == "critical"
    assert payload["runtime_resource"][
        "requires_attention"
    ] is True
    assert payload["runtime_resource"]["snapshot"][
        "cpu_percent"
    ] == 95.0


def test_dashboard_records_resource_reader_failure() -> None:
    snapshot = create_service(
        FailingResourceReader()
    ).create_snapshot()

    assert snapshot.runtime_resource is None
    assert snapshot.is_partial
    assert snapshot.unavailable_components == (
        "runtime_resource",
    )
