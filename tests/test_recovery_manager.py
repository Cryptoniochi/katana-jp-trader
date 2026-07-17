"""RecoveryManagerのテスト。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import pytest

from app.live.recovery_manager import RecoveryManager
from app.live.recovery_models import RecoveryStatus
from app.trading.order_models import OrderStatus


NOW = datetime(
    2026,
    7,
    17,
    6,
    0,
    tzinfo=timezone.utc,
)


@dataclass
class FakeOrderRecord:
    order_id: str
    broker_order_id: str | None
    status: OrderStatus
    created_at: datetime
    id: int


class FakeHealthService:
    def __init__(self) -> None:
        self.fail = False

    def require_ready(self, broker):
        if self.fail:
            raise RuntimeError("health failed")
        return object()


class FakeOrderRepository:
    def __init__(self, records) -> None:
        self.records = records

    def list_recent(
        self,
        *,
        limit=100,
        code=None,
        status=None,
        side=None,
    ):
        return [
            item
            for item in self.records
            if item.status is status
        ]


class FakeExecutionResult:
    def __init__(self, failed_count=0) -> None:
        self.failed_count = failed_count


class FakeExecutionService:
    def __init__(self) -> None:
        self.order_ids = ()
        self.failed_count = 0

    def reconcile_many(
        self,
        order_ids,
        *,
        continue_on_error=False,
    ):
        self.order_ids = order_ids
        return FakeExecutionResult(self.failed_count)


class FakePortfolioService:
    def __init__(self) -> None:
        self.snapshot = object()
        self.fail = False

    def create_snapshot(self, *, generated_at=None):
        if self.fail:
            raise RuntimeError("snapshot failed")
        return self.snapshot


class FakePortfolioRepository:
    def __init__(self) -> None:
        self.saved = None

    def save(self, snapshot):
        self.saved = snapshot
        return snapshot


class FakeAuditReport:
    def __init__(self, error_count=0) -> None:
        self.error_count = error_count
        self.has_errors = error_count > 0


class FakeAuditService:
    def __init__(self) -> None:
        self.error_count = 0
        self.snapshot = None

    def audit(self, *, local_portfolio=None):
        self.snapshot = local_portfolio
        return FakeAuditReport(self.error_count)


def create_manager(records=()):
    health = FakeHealthService()
    execution = FakeExecutionService()
    portfolio = FakePortfolioService()
    repository = FakePortfolioRepository()
    audit = FakeAuditService()

    manager = RecoveryManager(
        broker=object(),
        health_service=health,
        order_repository=FakeOrderRepository(
            list(records)
        ),
        execution_service=execution,
        portfolio_service=portfolio,
        portfolio_audit_service=audit,
        portfolio_repository=repository,
    )

    return (
        manager,
        health,
        execution,
        portfolio,
        repository,
        audit,
    )


def test_recovery_completes_without_active_orders() -> None:
    manager, *_ = create_manager()

    result = manager.recover()

    assert result.status is RecoveryStatus.COMPLETED
    assert result.failed_step_count == 0
    assert result.steps[1].status.value == "skipped"


def test_recovery_reconciles_active_orders() -> None:
    records = (
        FakeOrderRecord(
            order_id="order-1",
            broker_order_id="broker-1",
            status=OrderStatus.SENT,
            created_at=NOW,
            id=1,
        ),
        FakeOrderRecord(
            order_id="order-2",
            broker_order_id="broker-2",
            status=OrderStatus.PARTIALLY_FILLED,
            created_at=NOW,
            id=2,
        ),
    )
    manager, _health, execution, *_ = create_manager(
        records
    )

    result = manager.recover()

    assert result.is_successful
    assert execution.order_ids == (
        "order-1",
        "order-2",
    )


def test_recovery_ignores_active_order_without_broker_id() -> None:
    records = (
        FakeOrderRecord(
            order_id="order-1",
            broker_order_id=None,
            status=OrderStatus.SENT,
            created_at=NOW,
            id=1,
        ),
    )
    manager, _health, execution, *_ = create_manager(
        records
    )

    result = manager.recover()

    assert result.is_successful
    assert execution.order_ids == ()


def test_recovery_reports_portfolio_audit_errors() -> None:
    manager, *_rest, audit = create_manager()
    audit.error_count = 2

    result = manager.recover(
        continue_on_error=True
    )

    assert result.status is (
        RecoveryStatus.COMPLETED_WITH_ERRORS
    )
    assert result.failed_step_count == 1
    assert result.portfolio_audit_report.error_count == 2


def test_recovery_stops_on_health_failure_by_default() -> None:
    manager, health, *_ = create_manager()
    health.fail = True

    with pytest.raises(
        RuntimeError,
        match="health failed",
    ):
        manager.recover()


def test_recovery_continues_after_health_failure() -> None:
    manager, health, *_ = create_manager()
    health.fail = True

    result = manager.recover(
        continue_on_error=True
    )

    assert result.status is (
        RecoveryStatus.COMPLETED_WITH_ERRORS
    )
    assert result.failed_step_count == 1


def test_recovery_continues_after_snapshot_failure() -> None:
    manager, _health, _execution, portfolio, *_ = (
        create_manager()
    )
    portfolio.fail = True

    result = manager.recover(
        continue_on_error=True
    )

    assert result.status is (
        RecoveryStatus.COMPLETED_WITH_ERRORS
    )
    assert result.failed_step_count == 1
