"""DashboardWebServiceの辞書Snapshot対応テスト。"""

from datetime import datetime, timezone

from app.dashboard.dashboard_web_service import (
    DashboardWebService,
)


NOW = datetime(
    2026,
    7,
    18,
    0,
    0,
    tzinfo=timezone.utc,
)


class DictSnapshotReader:
    def create_snapshot(self):
        return {
            "generated_at": NOW.isoformat(),
            "complete": False,
            "partial": True,
            "errors": [],
            "portfolio": None,
            "broker": None,
        }


class EmptyHistoryReader:
    def list_recent(self, *, limit=30):
        return ()


def test_service_accepts_dictionary_snapshot() -> None:
    service = DashboardWebService(
        snapshot_reader=DictSnapshotReader(),
        daily_history_reader=EmptyHistoryReader(),
    )

    payload = service.create_payload()

    assert payload.generated_at == NOW
    assert payload.snapshot["partial"] is True
    assert payload.daily_history == ()
