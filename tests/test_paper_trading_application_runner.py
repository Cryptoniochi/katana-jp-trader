"""PaperTradingApplicationRunnerのテスト。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import pytest

from app.application.trading_loop_runner_models import (
    TradingLoopRunnerResult,
    TradingLoopRunnerStopReason,
)
from app.runtime.paper_trading_application_runner import (
    PaperTradingApplicationRunner,
)
from app.runtime.paper_trading_runtime_models import (
    PaperTradingDailySummary,
    PaperTradingRuntimeStatus,
)


NOW = datetime(
    2026,
    7,
    19,
    0,
    0,
    tzinfo=timezone.utc,
)


class FakeComponent:
    """開始・停止呼出を記録するComponent。"""

    def __init__(self) -> None:
        self.started = False
        self.stopped = False
        self.stop_error: Exception | None = None

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        if self.stop_error is not None:
            raise self.stop_error

        self.stopped = True


class FakeRuntime:
    """開始呼出を記録するRuntime。"""

    def __init__(self) -> None:
        self.started = False

    def start(self) -> None:
        self.started = True


class FakeMarketRunner:
    """固定結果または例外を返すMarket Runner。"""

    def __init__(
        self,
        result: TradingLoopRunnerResult,
    ) -> None:
        self.result = result
        self.error: Exception | None = None

    def run(self) -> TradingLoopRunnerResult:
        if self.error is not None:
            raise self.error

        return self.result


@dataclass(frozen=True, slots=True)
class FakePersistenceResult:
    """テスト用Persistence結果。"""

    summary: PaperTradingDailySummary


class FakePersistenceService:
    """正常・異常保存呼出を記録する。"""

    def __init__(self) -> None:
        self.completed = False
        self.failed_message: str | None = None

    def complete_and_persist(
        self,
    ) -> FakePersistenceResult:
        self.completed = True

        return FakePersistenceResult(
            summary=create_summary(
                status=PaperTradingRuntimeStatus.COMPLETED
            )
        )

    def fail_and_persist(
        self,
        *,
        error_message: str,
    ) -> FakePersistenceResult:
        self.failed_message = error_message

        return FakePersistenceResult(
            summary=create_summary(
                status=PaperTradingRuntimeStatus.FAILED,
                error_message=error_message,
            )
        )


def create_runner_result(
    stop_reason: TradingLoopRunnerStopReason,
    *,
    error_message: str | None = None,
) -> TradingLoopRunnerResult:
    """テスト用Runner結果を作成する。"""

    return TradingLoopRunnerResult(
        started_at=NOW,
        completed_at=NOW,
        stop_reason=stop_reason,
        cycles=(),
        error_message=error_message,
    )


def create_summary(
    *,
    status: PaperTradingRuntimeStatus,
    error_message: str | None = None,
) -> PaperTradingDailySummary:
    """テスト用日次サマリーを作成する。"""

    return PaperTradingDailySummary(
        trading_date=NOW.date(),
        started_at=NOW,
        completed_at=NOW,
        status=status,
        records=(),
        initial_equity=1_000_000.0,
        final_equity=1_000_000.0,
        error_message=error_message,
    )


def create_application(
    runner_result: TradingLoopRunnerResult,
):
    """テスト対象とFake依存を作成する。"""

    component = FakeComponent()
    runtime = FakeRuntime()
    market_runner = FakeMarketRunner(
        runner_result
    )
    persistence = FakePersistenceService()

    application = PaperTradingApplicationRunner(
        component=component,
        runtime=runtime,
        market_runner=market_runner,
        persistence_service=persistence,
    )

    return (
        application,
        component,
        runtime,
        market_runner,
        persistence,
    )


@pytest.mark.parametrize(
    "stop_reason",
    (
        TradingLoopRunnerStopReason.STOP_REQUESTED,
        TradingLoopRunnerStopReason.MAX_CYCLES_REACHED,
    ),
)
def test_normal_stop_completes_and_persists(
    stop_reason: TradingLoopRunnerStopReason,
) -> None:
    """通常停止では正常サマリーを保存する。"""

    (
        application,
        component,
        runtime,
        _market_runner,
        persistence,
    ) = create_application(
        create_runner_result(stop_reason)
    )

    result = application.run()

    assert component.started is True
    assert component.stopped is True
    assert runtime.started is True
    assert persistence.completed is True
    assert persistence.failed_message is None
    assert result.is_successful is True
    assert result.daily_summary.status is (
        PaperTradingRuntimeStatus.COMPLETED
    )


@pytest.mark.parametrize(
    "stop_reason",
    (
        TradingLoopRunnerStopReason.ERROR,
        TradingLoopRunnerStopReason.CYCLE_FAILED,
        TradingLoopRunnerStopReason.RESOURCE_CRITICAL,
    ),
)
def test_abnormal_stop_fails_and_persists(
    stop_reason: TradingLoopRunnerStopReason,
) -> None:
    """異常終了理由では失敗サマリーを保存する。"""

    error_message = (
        "runner failed"
        if stop_reason is TradingLoopRunnerStopReason.ERROR
        else None
    )

    (
        application,
        component,
        runtime,
        _market_runner,
        persistence,
    ) = create_application(
        create_runner_result(
            stop_reason,
            error_message=error_message,
        )
    )

    result = application.run()

    assert component.stopped is True
    assert runtime.started is True
    assert persistence.completed is False
    assert persistence.failed_message is not None
    assert result.is_successful is False
    assert result.daily_summary.status is (
        PaperTradingRuntimeStatus.FAILED
    )


def test_component_stop_failure_is_persisted_as_failure() -> None:
    """Component停止失敗を異常サマリーへ保存する。"""

    (
        application,
        component,
        _runtime,
        _market_runner,
        persistence,
    ) = create_application(
        create_runner_result(
            TradingLoopRunnerStopReason.STOP_REQUESTED
        )
    )
    component.stop_error = RuntimeError(
        "stop failed"
    )

    result = application.run()

    assert persistence.completed is False
    assert persistence.failed_message is not None
    assert "stop failed" in persistence.failed_message
    assert result.is_successful is False


def test_runner_exception_fails_and_persists_then_reraises() -> None:
    """Runner例外を保存した後で呼出元へ再送出する。"""

    (
        application,
        component,
        runtime,
        market_runner,
        persistence,
    ) = create_application(
        create_runner_result(
            TradingLoopRunnerStopReason.STOP_REQUESTED
        )
    )
    market_runner.error = RuntimeError(
        "market runner exploded"
    )

    with pytest.raises(
        RuntimeError,
        match="market runner exploded",
    ):
        application.run()

    assert component.stopped is True
    assert runtime.started is True
    assert persistence.failed_message is not None
    assert (
        "market runner exploded"
        in persistence.failed_message
    )