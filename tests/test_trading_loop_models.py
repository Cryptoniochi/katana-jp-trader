"""Trading Loopモデルのテスト。"""

from datetime import datetime, timezone

import pytest

from app.application.trading_loop_models import (
    TradingLoopCycleResult,
    TradingLoopCycleStatus,
    TradingLoopRunResult,
)
from app.live.live_orchestrator_models import (
    LiveCycleResult,
    LiveCycleStatus,
)
from app.runtime.session_models import (
    RuntimeSessionSnapshot,
    RuntimeSessionStatus,
)


NOW = datetime(
    2026,
    7,
    18,
    12,
    0,
    tzinfo=timezone.utc,
)


def runtime_snapshot() -> RuntimeSessionSnapshot:
    return RuntimeSessionSnapshot(
        session_id="session-1",
        status=RuntimeSessionStatus.RUNNING,
        started_at=NOW,
        checked_at=NOW,
        active_date=NOW.date(),
        cycle_count=1,
        successful_cycle_count=1,
        failed_cycle_count=0,
        heartbeat_count=1,
        restart_count=0,
        error_count=0,
        completed_day_count=0,
    )


def live_cycle(
    *,
    status: LiveCycleStatus,
) -> LiveCycleResult:
    return LiveCycleResult(
        cycle_number=1,
        started_at=NOW,
        completed_at=NOW,
        status=status,
        market_result=(
            object()
            if status is LiveCycleStatus.COMPLETED
            else None
        ),
        paper_trading_result=None,
        error_message=(
            "failed"
            if status is LiveCycleStatus.FAILED
            else None
        ),
    )


def test_completed_cycle_is_successful() -> None:
    result = TradingLoopCycleResult(
        cycle_number=1,
        started_at=NOW,
        completed_at=NOW,
        status=TradingLoopCycleStatus.COMPLETED,
        live_cycle_result=live_cycle(
            status=LiveCycleStatus.COMPLETED
        ),
        runtime_session_snapshot=runtime_snapshot(),
        resource_result=None,
    )

    assert result.is_successful
    assert result.signal_count == 0
    assert result.execution_count == 0


def test_failed_cycle_requires_error_message() -> None:
    with pytest.raises(
        ValueError,
        match="エラーメッセージ",
    ):
        TradingLoopCycleResult(
            cycle_number=1,
            started_at=NOW,
            completed_at=NOW,
            status=TradingLoopCycleStatus.FAILED,
            live_cycle_result=None,
            runtime_session_snapshot=runtime_snapshot(),
            resource_result=None,
        )


def test_run_result_requires_consecutive_numbers() -> None:
    first = TradingLoopCycleResult(
        cycle_number=1,
        started_at=NOW,
        completed_at=NOW,
        status=TradingLoopCycleStatus.COMPLETED,
        live_cycle_result=live_cycle(
            status=LiveCycleStatus.COMPLETED
        ),
        runtime_session_snapshot=runtime_snapshot(),
        resource_result=None,
    )
    second = TradingLoopCycleResult(
        cycle_number=3,
        started_at=NOW,
        completed_at=NOW,
        status=TradingLoopCycleStatus.FAILED,
        live_cycle_result=None,
        runtime_session_snapshot=runtime_snapshot(),
        resource_result=None,
        error_message="failed",
    )

    with pytest.raises(
        ValueError,
        match="連番",
    ):
        TradingLoopRunResult(
            cycles=(first, second)
        )
