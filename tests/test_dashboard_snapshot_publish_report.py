"""Dashboard Snapshot Publishレポートのテスト。"""

from datetime import datetime, timezone
from pathlib import Path

from app.dashboard.dashboard_models import (
    DashboardBrokerStatus,
    DashboardSnapshot,
)
from app.dashboard.dashboard_snapshot_publish_report import (
    dashboard_snapshot_publish_result_to_dict,
)
from app.dashboard.dashboard_snapshot_publish_service import (
    DashboardSnapshotPublishResult,
)
from app.dashboard.dashboard_snapshot_writer import (
    DashboardSnapshotWriteResult,
)


NOW = datetime(
    2026,
    7,
    18,
    0,
    0,
    tzinfo=timezone.utc,
)


def test_publish_result_is_json_compatible() -> None:
    snapshot = DashboardSnapshot(
        generated_at=NOW,
        system_health=None,
        runtime_metrics=None,
        portfolio=None,
        orders=None,
        live_summary=None,
        broker=DashboardBrokerStatus(
            connected=True,
            name="paper",
        ),
        errors=(),
    )
    result = DashboardSnapshotPublishResult(
        snapshot=snapshot,
        write_result=DashboardSnapshotWriteResult(
            output_path=Path(
                "reports/dashboard/dashboard.json"
            ),
            generated_at=NOW,
            size_bytes=123,
        ),
    )

    payload = dashboard_snapshot_publish_result_to_dict(
        result
    )

    assert payload["complete"] is True
    assert payload["partial"] is False
    assert payload["size_bytes"] == 123
    assert payload["unavailable_components"] == []
