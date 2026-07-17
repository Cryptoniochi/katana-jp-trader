"""DashboardFormatterのテスト。"""

from datetime import date, datetime, timezone

from app.dashboard.dashboard_formatter import DashboardFormatter
from app.dashboard.dashboard_models import (
    DashboardBrokerStatus,
    DashboardComponentError,
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
    18,
    0,
    0,
    tzinfo=timezone.utc,
)


def snapshot(
    *,
    with_errors: bool = False,
) -> DashboardSnapshot:
    return DashboardSnapshot(
        generated_at=NOW,
        system_health=None,
        runtime_metrics=RuntimeMetricsSnapshot(
            generated_at=NOW,
            counts={
                RuntimeMetricName.DOMAIN_EVENT_COUNT: 100,
                RuntimeMetricName.ERROR_OCCURRED_COUNT: 2,
                RuntimeMetricName.NOTIFICATION_DELIVERED_COUNT: 9,
                RuntimeMetricName.NOTIFICATION_FAILED_COUNT: 1,
            },
        ),
        portfolio=PortfolioSnapshot(
            currency="JPY",
            cash_balance=1_000_000.0,
            buying_power=800_000.0,
            broker_market_value=200_000.0,
            broker_equity=1_200_000.0,
            positions=(),
            generated_at=NOW,
        ),
        orders=DashboardOrderSummary(
            total_count=2,
            active_count=1,
            terminal_count=1,
            status_counts={
                OrderStatus.SENT: 1,
                OrderStatus.FILLED: 1,
            },
        ),
        live_summary=LiveDailyOperationSummary(
            trading_date=date(2026, 7, 18),
            log_count=5,
            cycle_started_count=1,
            cycle_completed_count=1,
            market_poll_count=1,
            signal_count=1,
            risk_rejected_count=0,
            risk_halted_count=0,
            order_count=2,
            execution_count=1,
            error_count=0,
            critical_count=0,
            codes=("7203",),
        ),
        broker=DashboardBrokerStatus(
            connected=True,
            name="paper",
        ),
        errors=(
            (
                DashboardComponentError(
                    component="system_health",
                    error_message="health unavailable",
                ),
            )
            if with_errors
            else ()
        ),
    )


def test_formatter_contains_core_sections() -> None:
    text = DashboardFormatter().format(snapshot())

    assert "Project KATANA Dashboard" in text
    assert "System Health" in text
    assert "Broker" in text
    assert "Portfolio" in text
    assert "Orders" in text
    assert "Runtime Metrics" in text
    assert "Live Summary" in text
    assert "CONNECTED" in text
    assert "1,000,000.00 JPY" in text
    assert "Error Rate           : 2.00%" in text


def test_formatter_displays_unavailable_components() -> None:
    text = DashboardFormatter().format(
        snapshot(with_errors=True)
    )

    assert "Status : UNAVAILABLE" in text
    assert "Unavailable Components" in text
    assert (
        "system_health: health unavailable"
        in text
    )
