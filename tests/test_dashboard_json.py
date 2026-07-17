"""Dashboard JSON変換のテスト。"""

import json
from datetime import date, datetime, timezone

from app.dashboard.dashboard_json import (
    dashboard_snapshot_to_dict,
)
from app.dashboard.dashboard_models import (
    DashboardBrokerStatus,
    DashboardOrderSummary,
    DashboardSnapshot,
)
from app.live.live_operation_log_models import (
    LiveDailyOperationSummary,
)
from app.monitoring.runtime_metrics import (
    RuntimeMetricName,
    RuntimeMetricsSnapshot,
)
from app.trading.order_models import OrderStatus
from app.trading.portfolio_models import PortfolioSnapshot


NOW = datetime(
    2026,
    7,
    17,
    6,
    0,
    tzinfo=timezone.utc,
)


def test_snapshot_converts_to_json_compatible_dict() -> None:
    snapshot = DashboardSnapshot(
        generated_at=NOW,
        system_health=None,
        runtime_metrics=RuntimeMetricsSnapshot(
            generated_at=NOW,
            counts={
                RuntimeMetricName.DOMAIN_EVENT_COUNT: 10,
                RuntimeMetricName.ERROR_OCCURRED_COUNT: 1,
            },
        ),
        portfolio=PortfolioSnapshot(
            currency="JPY",
            cash_balance=1_000_000.0,
            buying_power=900_000.0,
            broker_market_value=0.0,
            broker_equity=1_000_000.0,
            positions=(),
            generated_at=NOW,
        ),
        orders=DashboardOrderSummary(
            total_count=1,
            active_count=1,
            terminal_count=0,
            status_counts={
                OrderStatus.SENT: 1,
            },
        ),
        live_summary=LiveDailyOperationSummary(
            trading_date=date(2026, 7, 17),
            log_count=1,
            cycle_started_count=1,
            cycle_completed_count=0,
            market_poll_count=0,
            signal_count=0,
            risk_rejected_count=0,
            risk_halted_count=0,
            order_count=1,
            execution_count=0,
            error_count=0,
            critical_count=0,
            codes=("7203",),
        ),
        broker=DashboardBrokerStatus(
            connected=True,
            name="paper",
        ),
        errors=(),
    )

    payload = dashboard_snapshot_to_dict(snapshot)

    serialized = json.dumps(
        payload,
        ensure_ascii=False,
    )

    assert payload["complete"] is True
    assert payload["runtime_metrics"]["counts"][
        "domain_event_count"
    ] == 10
    assert payload["portfolio"]["currency"] == "JPY"
    assert payload["orders"]["status_counts"]["sent"] == 1
    assert payload["broker"]["connected"] is True
    assert "secret" not in serialized.lower()
