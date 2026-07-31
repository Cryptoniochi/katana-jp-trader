"""本番Risk Gateの統合強制テスト。"""

from app.backtest.queue_execution_service import (
    BacktestQueueExecutionBatchResult,
)
from app.risk.risk_aware_queue_execution_service import (
    RiskAwareQueueExecutionService,
)
from app.risk.paper_trading_pretrade_risk import (
    PaperTradingRiskDecision,
)


class FakeExecutionService:
    def __init__(self) -> None:
        self.call_count = 0

    def execute_all(
        self,
        *,
        limit=None,
        continue_on_error=True,
    ):
        self.call_count += 1
        return BacktestQueueExecutionBatchResult(items=())


def decision(*, allowed: bool) -> PaperTradingRiskDecision:
    return PaperTradingRiskDecision(
        allows_new_entries=allowed,
        is_blocked=not allowed,
        reason=(
            "entry_allowed"
            if allowed
            else "max_daily_loss_reached"
        ),
        daily_profit_loss=(
            0.0 if allowed else -100_001.0
        ),
        position_count=0,
        total_exposure=0.0,
        cash_balance=10_000_000.0,
        proposed_order_value=250_000.0,
        daily_entry_count=0,
    )


def test_blocked_risk_never_calls_execution_service() -> None:
    delegate = FakeExecutionService()
    service = RiskAwareQueueExecutionService(
        execution_service=delegate
    )

    result = service.execute_all(
        risk_result=decision(allowed=False)
    )

    assert result.was_blocked
    assert delegate.call_count == 0
    assert service.blocked_count == 1


def test_allowed_risk_calls_execution_service_once() -> None:
    delegate = FakeExecutionService()
    service = RiskAwareQueueExecutionService(
        execution_service=delegate
    )

    result = service.execute_all(
        risk_result=decision(allowed=True)
    )

    assert result.was_executed
    assert delegate.call_count == 1
    assert service.execution_count == 1
