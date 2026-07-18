"""DashboardWebServiceの日次可視化指標テスト。"""

from datetime import date, datetime, timezone

import pytest

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


class SnapshotReader:
    def create_snapshot(self):
        return {
            "generated_at": NOW.isoformat(),
            "complete": True,
            "partial": False,
            "errors": [],
            "portfolio": None,
            "broker": None,
        }


def record(
    *,
    day: int,
    initial_equity: float,
    final_equity: float,
) -> PaperTradingDailyRecord:
    timestamp = NOW.replace(day=day)
    profit = final_equity - initial_equity

    return PaperTradingDailyRecord(
        trading_date=date(2026, 7, day),
        status=PaperTradingRuntimeStatus.COMPLETED,
        started_at=timestamp,
        completed_at=timestamp,
        cycle_count=0,
        successful_cycle_count=0,
        failed_cycle_count=0,
        signal_count=0,
        execution_count=0,
        initial_equity=initial_equity,
        final_equity=final_equity,
        net_profit_loss=profit,
        return_rate=profit / initial_equity,
        error_message=None,
        payload={},
        created_at=timestamp,
        updated_at=timestamp,
    )


class HistoryReader:
    def list_recent(self, *, limit=30):
        return (
            record(
                day=18,
                initial_equity=1_100_000.0,
                final_equity=1_050_000.0,
            ),
            record(
                day=17,
                initial_equity=1_000_000.0,
                final_equity=1_100_000.0,
            ),
        )


def test_service_calculates_cumulative_and_drawdown() -> None:
    service = DashboardWebService(
        snapshot_reader=SnapshotReader(),
        daily_history_reader=HistoryReader(),
    )

    payload = service.create_payload()
    first, second = payload.daily_history

    assert first.trading_date.isoformat() == "2026-07-17"
    assert first.cumulative_profit_loss == 100_000.0
    assert first.drawdown == 0.0
    assert second.cumulative_profit_loss == 50_000.0
    assert second.drawdown == pytest.approx(
        (1_100_000.0 - 1_050_000.0)
        / 1_100_000.0
    )
    assert second.cumulative_return == pytest.approx(0.05)
    assert payload.maximum_drawdown == second.drawdown
