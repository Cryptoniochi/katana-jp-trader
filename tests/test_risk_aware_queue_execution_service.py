"""RiskAwareQueueExecutionServiceのテスト。"""

from dataclasses import dataclass

import pytest

from app.backtest.queue_execution_service import (
    BacktestQueueExecutionBatchResult,
)
from app.risk.risk_aware_queue_execution_service import (
    RiskAwareQueueExecutionDecision,
    RiskAwareQueueExecutionResult,
    RiskAwareQueueExecutionService,
)


@dataclass(frozen=True)
class FakeRiskResult:
    """テスト用Risk結果。"""

    allows_new_entries: bool
    is_blocked: bool


class FakeExecutionService:
    """注文キュー執行呼び出しを記録する。"""

    def __init__(
        self,
        *,
        result: BacktestQueueExecutionBatchResult | None = None,
    ) -> None:
        self.result = (
            result
            if result is not None
            else BacktestQueueExecutionBatchResult(items=())
        )
        self.calls: list[dict[str, object]] = []

    def execute_all(
        self,
        *,
        limit: int | None = None,
        continue_on_error: bool = True,
    ) -> BacktestQueueExecutionBatchResult:
        self.calls.append(
            {
                "limit": limit,
                "continue_on_error": continue_on_error,
            }
        )
        return self.result


def allowed_risk() -> FakeRiskResult:
    """注文を許可するRisk結果を返す。"""

    return FakeRiskResult(
        allows_new_entries=True,
        is_blocked=False,
    )


def blocked_risk() -> FakeRiskResult:
    """注文を停止するRisk結果を返す。"""

    return FakeRiskResult(
        allows_new_entries=False,
        is_blocked=True,
    )


def test_executes_delegate_when_risk_allows() -> None:
    """Risk許可時は既存執行サービスを呼び出す。"""

    delegate = FakeExecutionService()
    service = RiskAwareQueueExecutionService(
        execution_service=delegate,
    )

    result = service.execute_all(
        risk_result=allowed_risk(),
        limit=3,
        continue_on_error=False,
    )

    assert result.decision is (
        RiskAwareQueueExecutionDecision.EXECUTED
    )
    assert result.was_executed
    assert not result.was_blocked
    assert result.execution_result is delegate.result
    assert delegate.calls == [
        {
            "limit": 3,
            "continue_on_error": False,
        }
    ]


def test_does_not_execute_delegate_when_risk_blocks() -> None:
    """Risk停止時はBroker執行処理を呼び出さない。"""

    delegate = FakeExecutionService()
    service = RiskAwareQueueExecutionService(
        execution_service=delegate,
    )

    result = service.execute_all(
        risk_result=blocked_risk(),
    )

    assert result.decision is (
        RiskAwareQueueExecutionDecision.BLOCKED
    )
    assert result.was_blocked
    assert not result.was_executed
    assert result.execution_result is None
    assert result.processed_count == 0
    assert result.saved_execution_count == 0
    assert result.message is not None
    assert "Brokerへ送信しませんでした" in result.message
    assert delegate.calls == []


def test_tracks_execution_and_blocked_counts() -> None:
    """Broker執行回数とリスク停止回数を分けて保持する。"""

    service = RiskAwareQueueExecutionService(
        execution_service=FakeExecutionService(),
    )

    assert service.execution_count == 0
    assert service.blocked_count == 0
    assert service.last_result is None

    executed = service.execute_all(
        risk_result=allowed_risk(),
    )
    blocked = service.execute_all(
        risk_result=blocked_risk(),
    )

    assert service.execution_count == 1
    assert service.blocked_count == 1
    assert service.last_result is blocked
    assert service.last_result is not executed


def test_forwards_batch_result_properties() -> None:
    """実際のBatch結果に関する集計値を透過的に返す。"""

    batch = BacktestQueueExecutionBatchResult(items=())
    service = RiskAwareQueueExecutionService(
        execution_service=FakeExecutionService(
            result=batch,
        ),
    )

    result = service.execute_all(
        risk_result=allowed_risk(),
    )

    assert result.processed_count == 0
    assert result.terminal_count == 0
    assert result.active_count == 0
    assert result.failed_count == 0
    assert result.saved_execution_count == 0
    assert result.is_successful


def test_blocked_result_is_not_successful() -> None:
    """Risk停止結果は正常執行扱いにしない。"""

    service = RiskAwareQueueExecutionService(
        execution_service=FakeExecutionService(),
    )

    result = service.execute_all(
        risk_result=blocked_risk(),
    )

    assert not result.is_successful


@pytest.mark.parametrize(
    "limit",
    (
        0,
        -1,
    ),
)
def test_rejects_invalid_limit(limit: int) -> None:
    """不正な処理件数を拒否する。"""

    service = RiskAwareQueueExecutionService(
        execution_service=FakeExecutionService(),
    )

    with pytest.raises(
        ValueError,
        match="処理件数は0より大きい必要があります。",
    ):
        service.execute_all(
            risk_result=allowed_risk(),
            limit=limit,
        )


@pytest.mark.parametrize(
    "risk_result",
    (
        FakeRiskResult(
            allows_new_entries=True,
            is_blocked=True,
        ),
        FakeRiskResult(
            allows_new_entries=False,
            is_blocked=False,
        ),
    ),
)
def test_rejects_inconsistent_risk_state(
    risk_result: FakeRiskResult,
) -> None:
    """矛盾したRisk状態を拒否する。"""

    service = RiskAwareQueueExecutionService(
        execution_service=FakeExecutionService(),
    )

    with pytest.raises(
        ValueError,
        match="Risk結果のallows_new_entriesとis_blockedが矛盾",
    ):
        service.execute_all(
            risk_result=risk_result,
        )


def test_result_rejects_executed_without_batch() -> None:
    """EXECUTED結果にBatchがない状態を拒否する。"""

    with pytest.raises(
        ValueError,
        match="EXECUTED結果には注文執行結果が必要です。",
    ):
        RiskAwareQueueExecutionResult(
            decision=(
                RiskAwareQueueExecutionDecision.EXECUTED
            ),
            execution_result=None,
        )


def test_result_rejects_blocked_with_batch() -> None:
    """BLOCKED結果にBatchが設定された状態を拒否する。"""

    with pytest.raises(
        ValueError,
        match="BLOCKED結果には注文執行結果を設定できません。",
    ):
        RiskAwareQueueExecutionResult(
            decision=(
                RiskAwareQueueExecutionDecision.BLOCKED
            ),
            execution_result=(
                BacktestQueueExecutionBatchResult(items=())
            ),
            message="blocked",
        )


def test_result_rejects_blocked_without_message() -> None:
    """BLOCKED結果に停止理由がない状態を拒否する。"""

    with pytest.raises(
        ValueError,
        match="BLOCKED結果には停止理由が必要です。",
    ):
        RiskAwareQueueExecutionResult(
            decision=(
                RiskAwareQueueExecutionDecision.BLOCKED
            ),
            execution_result=None,
            message=" ",
        )
