"""DashboardWebServiceのテスト。"""

from datetime import date, datetime, timezone

from app.dashboard.dashboard_models import (
    DashboardBrokerStatus,
    DashboardSnapshot,
)
from app.dashboard.dashboard_web_service import (
    DashboardWebService,
)
from app.runtime.paper_trading_daily_repository import (
    PaperTradingDailyRecord,
)
from app.runtime.paper_trading_runtime_models import (
    PaperTradingRuntimeStatus,
)


NOW = datetime(
    2026,
    7,
    18,
    0,
    0,
    tzinfo=timezone.utc,
)


class FakeSnapshotReader:
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


def daily_record(
    day: int,
    profit: float,
) -> PaperTradingDailyRecord:
    value = NOW.replace(day=day)

    return PaperTradingDailyRecord(
        trading_date=date(2026, 7, day),
        status=PaperTradingRuntimeStatus.COMPLETED,
        started_at=value,
        completed_at=value,
        cycle_count=0,
        successful_cycle_count=0,
        failed_cycle_count=0,
        signal_count=0,
        execution_count=0,
        initial_equity=1_000_000.0,
        final_equity=1_000_000.0 + profit,
        net_profit_loss=profit,
        return_rate=profit / 1_000_000.0,
        error_message=None,
        payload={},
        created_at=value,
        updated_at=value,
    )


class FakeHistoryReader:
    def list_recent(self, *, limit=30):
        assert limit == 2
        return (
            daily_record(18, 10_000.0),
            daily_record(17, -2_000.0),
        )


def test_service_builds_chronological_history() -> None:
    service = DashboardWebService(
        snapshot_reader=FakeSnapshotReader(),
        daily_history_reader=FakeHistoryReader(),
        history_limit=2,
    )

    payload = service.create_payload()

    assert [
        point.trading_date.isoformat()
        for point in payload.daily_history
    ] == [
        "2026-07-17",
        "2026-07-18",
    ]
    assert payload.cumulative_profit_loss == 8_000.0
    assert payload.snapshot["broker"]["name"] == "paper"
