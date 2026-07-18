"""DashboardへのRuntime Health統合テスト。"""

from datetime import datetime, timezone

from app.dashboard.dashboard_json import (
    dashboard_snapshot_to_dict,
)
from app.dashboard.dashboard_models import (
    DashboardSnapshot,
)
from app.runtime.runtime_health_monitor_models import (
    RuntimeHealthMonitorReport,
    RuntimeHealthStatus,
)


NOW = datetime(
    2026,
    7,
    18,
    0,
    0,
    tzinfo=timezone.utc,
)


def test_dashboard_json_contains_runtime_health() -> None:
    health = RuntimeHealthMonitorReport(
        status=RuntimeHealthStatus.WARNING,
        checked_at=NOW,
        running=True,
        heartbeat_age_seconds=100.0,
        cycle_age_seconds=20.0,
        reasons=("Heartbeatが停滞しています。",),
    )
    snapshot = DashboardSnapshot(
        generated_at=NOW,
        system_health=None,
        runtime_metrics=None,
        portfolio=None,
        orders=None,
        live_summary=None,
        broker=None,
        errors=(),
        runtime_health=health,
    )

    payload = dashboard_snapshot_to_dict(snapshot)

    assert payload["runtime_health"]["status"] == "warning"
    assert payload["runtime_health"]["requires_attention"] is True
    assert payload["runtime_health"]["heartbeat_age_seconds"] == 100.0
