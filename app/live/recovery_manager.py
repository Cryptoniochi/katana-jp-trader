"""ライブ運転開始前にBroker・注文・約定・ポートフォリオを復旧する。"""

from __future__ import annotations

from typing import Protocol

from app.broker.broker_health_models import BrokerHealthCheckResult
from app.live.live_execution_reconciliation_service import (
    LiveExecutionReconciliationBatchResult,
)
from app.live.recovery_models import (
    RecoveryResult,
    RecoveryStatus,
    RecoveryStepResult,
    RecoveryStepStatus,
)
from app.trading.order_models import (
    OrderStatus,
    TradeOrderRecord,
)
from app.trading.portfolio_audit_models import PortfolioAuditReport
from app.trading.portfolio_models import PortfolioSnapshot


class RecoveryBrokerHealthService(Protocol):
    def require_ready(
        self,
        broker,
    ) -> BrokerHealthCheckResult:
        """Brokerが復旧処理に利用可能か確認する。"""


class RecoveryOrderRepository(Protocol):
    def list_recent(
        self,
        *,
        limit: int = 100,
        code=None,
        status: OrderStatus | None = None,
        side=None,
    ) -> list[TradeOrderRecord]:
        """注文一覧を返す。"""


class RecoveryExecutionService(Protocol):
    def reconcile_many(
        self,
        order_ids: tuple[str, ...],
        *,
        continue_on_error: bool = False,
    ) -> LiveExecutionReconciliationBatchResult:
        """複数注文の増分約定を復旧する。"""


class RecoveryPortfolioService(Protocol):
    def create_snapshot(
        self,
        *,
        generated_at=None,
    ) -> PortfolioSnapshot:
        """現在のPortfolio Snapshotを作成する。"""


class RecoveryPortfolioAuditService(Protocol):
    def audit(
        self,
        *,
        local_portfolio: PortfolioSnapshot | None = None,
    ) -> PortfolioAuditReport:
        """Brokerとローカル状態を監査する。"""


class RecoveryPortfolioRepository(Protocol):
    def save(
        self,
        snapshot: PortfolioSnapshot,
    ) -> PortfolioSnapshot:
        """Portfolio Snapshotを保存する。"""


class RecoveryManager:
    """新規発注を行わず、読み取りと再照合だけで状態を復旧する。"""

    ACTIVE_ORDER_STATUSES = (
        OrderStatus.SENT,
        OrderStatus.PARTIALLY_FILLED,
    )

    def __init__(
        self,
        *,
        broker,
        health_service: RecoveryBrokerHealthService,
        order_repository: RecoveryOrderRepository,
        execution_service: RecoveryExecutionService,
        portfolio_service: RecoveryPortfolioService,
        portfolio_audit_service: RecoveryPortfolioAuditService,
        portfolio_repository: RecoveryPortfolioRepository,
    ) -> None:
        self.broker = broker
        self.health_service = health_service
        self.order_repository = order_repository
        self.execution_service = execution_service
        self.portfolio_service = portfolio_service
        self.portfolio_audit_service = portfolio_audit_service
        self.portfolio_repository = portfolio_repository

    def recover(
        self,
        *,
        continue_on_error: bool = False,
    ) -> RecoveryResult:
        steps: list[RecoveryStepResult] = []
        health_result: BrokerHealthCheckResult | None = None
        execution_result: (
            LiveExecutionReconciliationBatchResult | None
        ) = None
        portfolio_report: PortfolioAuditReport | None = None

        try:
            health_result = self.health_service.require_ready(
                self.broker
            )
            steps.append(
                RecoveryStepResult(
                    name="broker_health",
                    status=RecoveryStepStatus.COMPLETED,
                )
            )
        except Exception as error:
            steps.append(
                RecoveryStepResult(
                    name="broker_health",
                    status=RecoveryStepStatus.FAILED,
                    message=str(error),
                )
            )
            if not continue_on_error:
                raise

        try:
            active_orders = self._load_active_orders()
            order_ids = tuple(
                record.order_id
                for record in active_orders
                if record.broker_order_id is not None
            )

            if order_ids:
                execution_result = (
                    self.execution_service.reconcile_many(
                        order_ids,
                        continue_on_error=continue_on_error,
                    )
                )
                status = (
                    RecoveryStepStatus.FAILED
                    if execution_result.failed_count > 0
                    else RecoveryStepStatus.COMPLETED
                )
                message = (
                    f"{execution_result.failed_count}件の"
                    "約定復旧に失敗しました。"
                    if execution_result.failed_count > 0
                    else None
                )
            else:
                status = RecoveryStepStatus.SKIPPED
                message = "復旧対象の有効注文はありません。"

            steps.append(
                RecoveryStepResult(
                    name="execution_reconciliation",
                    status=status,
                    message=message,
                )
            )
        except Exception as error:
            steps.append(
                RecoveryStepResult(
                    name="execution_reconciliation",
                    status=RecoveryStepStatus.FAILED,
                    message=str(error),
                )
            )
            if not continue_on_error:
                raise

        try:
            snapshot = self.portfolio_service.create_snapshot()
            saved_snapshot = self.portfolio_repository.save(
                snapshot
            )
            steps.append(
                RecoveryStepResult(
                    name="portfolio_snapshot",
                    status=RecoveryStepStatus.COMPLETED,
                )
            )

            portfolio_report = (
                self.portfolio_audit_service.audit(
                    local_portfolio=saved_snapshot
                )
            )
            audit_status = (
                RecoveryStepStatus.FAILED
                if portfolio_report.has_errors
                else RecoveryStepStatus.COMPLETED
            )
            audit_message = (
                f"{portfolio_report.error_count}件の"
                "Portfolio差異を検出しました。"
                if portfolio_report.has_errors
                else None
            )
            steps.append(
                RecoveryStepResult(
                    name="portfolio_audit",
                    status=audit_status,
                    message=audit_message,
                )
            )
        except Exception as error:
            steps.append(
                RecoveryStepResult(
                    name="portfolio_snapshot",
                    status=RecoveryStepStatus.FAILED,
                    message=str(error),
                )
            )
            if not continue_on_error:
                raise

        failed_count = sum(
            step.is_failed
            for step in steps
        )

        if failed_count == 0:
            status = RecoveryStatus.COMPLETED
        elif continue_on_error:
            status = RecoveryStatus.COMPLETED_WITH_ERRORS
        else:
            status = RecoveryStatus.FAILED

        return RecoveryResult(
            status=status,
            steps=tuple(steps),
            health_result=health_result,
            execution_result=execution_result,
            portfolio_audit_report=portfolio_report,
        )

    def _load_active_orders(
        self,
    ) -> list[TradeOrderRecord]:
        records: list[TradeOrderRecord] = []

        for status in self.ACTIVE_ORDER_STATUSES:
            records.extend(
                self.order_repository.list_recent(
                    limit=10_000,
                    status=status,
                )
            )

        unique = {
            record.order_id: record
            for record in records
        }

        return sorted(
            unique.values(),
            key=lambda record: (
                record.created_at,
                record.id,
            ),
        )
