"""DashboardServiceのテスト。"""

from datetime import date, datetime, timezone

from app.dashboard.dashboard_models import (
    DashboardBrokerStatus,
)
from app.dashboard.dashboard_service import DashboardService
from app.live.live_operation_log_models import (
    LiveDailyOperationSummary,
)
from app.monitoring.runtime_metrics import (
    RuntimeMetricsSnapshot,
)
from app.monitoring.system_health_models import (
    SystemHealthReport,
    SystemHealthStatus,
)
from app.monitoring.update_health_service import (
    UpdateHealthReport,
    UpdateHealthStatus,
)
from app.trading.order_models import (
    OrderSide,
    OrderStatus,
    OrderType,
    TradeOrder,
    TradeOrderRecord,
)
from app.trading.portfolio_models import PortfolioSnapshot


NOW = datetime(
    2026,
    7,
    17,
    6,
    0,
    tzinfo=timezone.utc,
)


def health_report() -> SystemHealthReport:
    return SystemHealthReport(
        status=SystemHealthStatus.HEALTHY,
        checked_at=NOW,
        update_health=UpdateHealthReport(
            status=UpdateHealthStatus.HEALTHY,
            checked_at=NOW,
            reason="healthy",
            latest_run=None,
            latest_success=None,
            consecutive_failure_count=0,
            seconds_since_latest_run=None,
            seconds_since_latest_success=None,
        ),
        runtime_metrics=RuntimeMetricsSnapshot(
            generated_at=NOW,
            counts={},
        ),
        reasons=(),
    )


def portfolio_snapshot() -> PortfolioSnapshot:
    return PortfolioSnapshot(
        currency="JPY",
        cash_balance=1_000_000.0,
        buying_power=900_000.0,
        broker_market_value=0.0,
        broker_equity=1_000_000.0,
        positions=(),
        generated_at=NOW,
    )


def order_record(
    *,
    record_id: int,
    status: OrderStatus,
) -> TradeOrderRecord:
    terminal = status.is_terminal

    return TradeOrderRecord(
        id=record_id,
        order=TradeOrder(
            order_id=f"order-{record_id}",
            signal_id=f"signal-{record_id}",
            code="7203",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=100,
        ),
        status=status,
        filled_quantity=(
            100
            if status is OrderStatus.FILLED
            else 0
        ),
        average_fill_price=(
            2500.0
            if status is OrderStatus.FILLED
            else None
        ),
        broker_order_id=None,
        status_reason=None,
        error_message=None,
        created_at=NOW,
        updated_at=NOW,
        submitted_at=None,
        completed_at=NOW if terminal else None,
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
        return list(self.value)

    def summarize_date(self, _target_date):
        return self.value

    def get_dashboard_status(self):
        return self.value


class FailingReader:
    def check(self):
        raise RuntimeError("health failed")

    def snapshot(self):
        raise RuntimeError("metrics failed")

    def create_snapshot(self, *, generated_at=None):
        raise RuntimeError("portfolio failed")

    def list_recent(self, **_kwargs):
        raise RuntimeError("orders failed")

    def summarize_date(self, _target_date):
        raise RuntimeError("summary failed")

    def get_dashboard_status(self):
        raise RuntimeError("broker failed")


def live_summary() -> LiveDailyOperationSummary:
    return LiveDailyOperationSummary(
        trading_date=date(2026, 7, 17),
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
    )


def test_service_creates_complete_snapshot() -> None:
    service = DashboardService(
        system_health_reader=ValueReader(
            health_report()
        ),
        runtime_metrics_reader=ValueReader(
            RuntimeMetricsSnapshot(
                generated_at=NOW,
                counts={},
            )
        ),
        portfolio_reader=ValueReader(
            portfolio_snapshot()
        ),
        order_reader=ValueReader(
            (
                order_record(
                    record_id=1,
                    status=OrderStatus.SENT,
                ),
                order_record(
                    record_id=2,
                    status=OrderStatus.FILLED,
                ),
            )
        ),
        live_summary_reader=ValueReader(
            live_summary()
        ),
        broker_reader=ValueReader(
            DashboardBrokerStatus(
                connected=True,
                name="paper",
            )
        ),
        now_provider=lambda: NOW,
    )

    snapshot = service.create_snapshot()

    assert snapshot.is_complete
    assert snapshot.orders is not None
    assert snapshot.orders.total_count == 2
    assert snapshot.orders.active_count == 1
    assert snapshot.orders.terminal_count == 1
    assert snapshot.generated_at == NOW


def test_service_returns_partial_snapshot_on_failures() -> None:
    service = DashboardService(
        system_health_reader=FailingReader(),
        runtime_metrics_reader=ValueReader(
            RuntimeMetricsSnapshot(
                generated_at=NOW,
                counts={},
            )
        ),
        portfolio_reader=FailingReader(),
        order_reader=ValueReader(()),
        live_summary_reader=FailingReader(),
        broker_reader=ValueReader(
            DashboardBrokerStatus(
                connected=True,
                name="paper",
            )
        ),
        now_provider=lambda: NOW,
    )

    snapshot = service.create_snapshot()

    assert snapshot.is_partial
    assert snapshot.system_health is None
    assert snapshot.portfolio is None
    assert snapshot.live_summary is None
    assert snapshot.runtime_metrics is not None
    assert snapshot.orders is not None
    assert snapshot.broker is not None
    assert snapshot.unavailable_components == (
        "system_health",
        "portfolio",
        "live_summary",
    )


def test_service_rejects_naive_clock() -> None:
    service = DashboardService(
        system_health_reader=ValueReader(
            health_report()
        ),
        runtime_metrics_reader=ValueReader(
            RuntimeMetricsSnapshot(
                generated_at=NOW,
                counts={},
            )
        ),
        portfolio_reader=ValueReader(
            portfolio_snapshot()
        ),
        order_reader=ValueReader(()),
        live_summary_reader=ValueReader(
            live_summary()
        ),
        broker_reader=ValueReader(
            DashboardBrokerStatus(
                connected=True,
                name="paper",
            )
        ),
        now_provider=lambda: datetime(2026, 7, 17),
    )

    try:
        service.create_snapshot()
    except ValueError as error:
        assert "タイムゾーン" in str(error)
    else:
        raise AssertionError("ValueErrorが必要です。")
