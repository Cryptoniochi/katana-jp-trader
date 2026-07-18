"""DashboardSnapshotPublishServiceのテスト。"""

from datetime import datetime, timezone

from app.dashboard.dashboard_models import (
    DashboardBrokerStatus,
    DashboardSnapshot,
)
from app.dashboard.dashboard_snapshot_publish_service import (
    DashboardSnapshotPublishService,
)
from app.dashboard.dashboard_snapshot_writer import (
    DashboardSnapshotWriter,
)


NOW = datetime(
    2026,
    7,
    18,
    0,
    0,
    tzinfo=timezone.utc,
)


class FakeProvider:
    """テスト用Snapshot Provider。"""

    def create_snapshot(self) -> DashboardSnapshot:
        return DashboardSnapshot(
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


def test_service_creates_and_writes_snapshot(
    tmp_path,
) -> None:
    output_path = tmp_path / "dashboard.json"
    service = DashboardSnapshotPublishService(
        snapshot_provider=FakeProvider(),
        snapshot_writer=DashboardSnapshotWriter(
            output_path=output_path
        ),
    )

    result = service.publish()

    assert result.snapshot.generated_at == NOW
    assert result.write_result.output_path == output_path
    assert output_path.exists()
