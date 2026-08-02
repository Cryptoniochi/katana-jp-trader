"""RealtimePaperTradingServiceのテスト。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.backtest.backtest_portfolio_update_service import (
    BacktestPortfolioBatchUpdateResult,
)
from app.backtest.order_queue_service import (
    BacktestOrderQueueDecision,
    BacktestOrderQueueResult,
)
from app.backtest.queue_execution_service import (
    BacktestQueueExecutionBatchResult,
)
from app.dynamic_watchlist.strategy_routing_models import (
    StrategyRoutingSnapshot,
    SymbolStrategyRoute,
)
from app.market.models import StockPrice
from app.market.realtime_paper_trading_service import (
    RealtimePaperTradingService,
    RealtimePaperTradingStatus,
)
from app.market.realtime_signal_engine import (
    RealtimeSignalEngine,
)
from app.market.symbol_strategy_router import (
    SymbolStrategyRouter,
)
from app.risk.risk_aware_queue_execution_service import (
    RiskAwareQueueExecutionDecision,
    RiskAwareQueueExecutionResult,
)
from app.trading.order_models import OrderType
from app.trading.signal_models import (
    SignalAction,
    TradeSignal,
)


JST = ZoneInfo("Asia/Tokyo")


def price(
    minute: int,
    *,
    high: float,
    low: float,
    close: float,
) -> StockPrice:
    """ORB用5分足を作成する。"""

    return StockPrice(
        code="7203",
        datetime=datetime(
            2026,
            7,
            17,
            9,
            minute,
            tzinfo=JST,
        ),
        open=1000.0,
        high=high,
        low=low,
        close=close,
        volume=1000,
    )


def bars() -> tuple[StockPrice, ...]:
    """BUYシグナルを生成する系列を返す。"""

    return (
        price(0, high=1000.0, low=990.0, close=995.0),
        price(5, high=1000.0, low=990.0, close=998.0),
        price(10, high=1000.0, low=995.0, close=999.0),
        price(15, high=1000.0, low=995.0, close=999.0),
        price(20, high=1010.0, low=999.0, close=1005.0),
    )


@dataclass
class FakeExecutionItem:
    """保存済み約定を持つ簡易執行結果。"""

    execution_record: object | None = None
    is_failed: bool = False
    message: str | None = None


class FakeExecutionBatch:
    """実サービスが参照する執行結果プロパティを提供する。"""

    def __init__(
        self,
        items: tuple[FakeExecutionItem, ...] = (),
    ) -> None:
        self.items = items

    @property
    def failed_count(self) -> int:
        return sum(item.is_failed for item in self.items)


class FakeQueueService:
    """シグナルを受け取った順に記録する。"""

    def __init__(self) -> None:
        self.signals: list[TradeSignal] = []
        self.order_types: list[OrderType] = []
        self.fail = False

    def enqueue_signal(
        self,
        signal: TradeSignal,
        *,
        order_type: OrderType,
        continue_on_error: bool,
    ) -> BacktestOrderQueueResult:
        self.signals.append(signal)
        self.order_types.append(order_type)

        return BacktestOrderQueueResult(
            decision=(
                BacktestOrderQueueDecision.FAILED
                if self.fail
                else BacktestOrderQueueDecision.ENQUEUED
            ),
            signal=signal,
            order_record=None,
            queued_order=None,
            message="queue failed" if self.fail else None,
        )


class FakeExecutionService:
    """注文執行呼出回数を記録する。"""

    def __init__(self) -> None:
        self.call_count = 0
        self.fail = False

    def execute_all(
        self,
        *,
        continue_on_error: bool,
    ) -> FakeExecutionBatch:
        self.call_count += 1

        if self.fail:
            return FakeExecutionBatch(
                (
                    FakeExecutionItem(
                        is_failed=True,
                        message="execution failed",
                    ),
                )
            )

        return FakeExecutionBatch(())


@dataclass(frozen=True)
class FakeRiskResult:
    """注文執行可否を示すRisk結果。"""

    allows_new_entries: bool
    is_blocked: bool


class FakeRiskAwareExecutionService:
    """Risk Gate呼び出しを記録する。"""

    def __init__(
        self,
        *,
        blocked: bool,
    ) -> None:
        self.blocked = blocked
        self.calls = []

    def execute_all(
        self,
        *,
        risk_result,
        continue_on_error: bool,
    ) -> RiskAwareQueueExecutionResult:
        self.calls.append(
            {
                "risk_result": risk_result,
                "continue_on_error": continue_on_error,
            }
        )

        if self.blocked:
            return RiskAwareQueueExecutionResult(
                decision=(
                    RiskAwareQueueExecutionDecision.BLOCKED
                ),
                execution_result=None,
                message="risk blocked",
            )

        return RiskAwareQueueExecutionResult(
            decision=(
                RiskAwareQueueExecutionDecision.EXECUTED
            ),
            execution_result=(
                BacktestQueueExecutionBatchResult(items=())
            ),
            message=None,
        )


class FakePortfolioResult:
    """空のポートフォリオ更新結果。"""

    items: tuple[object, ...] = ()


class FakePortfolioService:
    """約定反映呼出回数を記録する。"""

    def __init__(self) -> None:
        self.call_count = 0
        self.limits: list[int] = []

    def apply_executions(
        self,
        records: tuple[object, ...],
        *,
        equity_curve_limit: int,
    ) -> FakePortfolioResult:
        self.call_count += 1
        self.limits.append(equity_curve_limit)
        return FakePortfolioResult()


def create_service(
    *,
    risk_aware_execution_service=None,
    risk_result_provider=None,
):
    """テスト対象と各Fakeを作成する。"""

    queue = FakeQueueService()
    execution = FakeExecutionService()
    portfolio = FakePortfolioService()
    prices: list[tuple[str, float]] = []
    clocks: list[datetime] = []

    service = RealtimePaperTradingService(
        signal_engine=RealtimeSignalEngine(),
        order_queue_service=queue,
        queue_execution_service=execution,
        portfolio_update_service=portfolio,
        market_price_updater=lambda code, value: (
            prices.append((code, value))
        ),
        clock_updater=clocks.append,
        risk_aware_execution_service=(
            risk_aware_execution_service
        ),
        risk_result_provider=risk_result_provider,
    )

    return (
        service,
        queue,
        execution,
        portfolio,
        prices,
        clocks,
    )


def test_service_runs_signal_to_order_pipeline() -> None:
    """BUYシグナルを注文・執行・資産更新へ流す。"""

    (
        service,
        queue,
        execution,
        _portfolio,
        updated_prices,
        clocks,
    ) = create_service()

    result = service.process(bars())

    assert result.is_completed
    assert result.signal_count == 1
    assert result.queued_count == 1
    assert queue.signals[0].action is SignalAction.BUY
    assert execution.call_count == 1
    assert len(updated_prices) == 5
    assert len(clocks) == 5
    assert result.risk_evaluated_count == 0


def test_service_uses_risk_gate_when_configured() -> None:
    """Risk Gate設定時は従来執行サービスを直接呼ばない。"""

    risk_result = FakeRiskResult(
        allows_new_entries=True,
        is_blocked=False,
    )
    gate = FakeRiskAwareExecutionService(
        blocked=False,
    )
    (
        service,
        _queue,
        execution,
        _portfolio,
        _prices,
        _clocks,
    ) = create_service(
        risk_aware_execution_service=gate,
        risk_result_provider=lambda: risk_result,
    )

    result = service.process(bars())

    assert execution.call_count == 0
    assert len(gate.calls) == 1
    assert gate.calls[0]["risk_result"] is risk_result
    assert result.risk_evaluated_count == 1
    assert result.risk_blocked_count == 0
    assert not result.was_risk_blocked


def test_service_blocks_broker_send_when_risk_blocks() -> None:
    """Risk BLOCKED時はBroker送信とPortfolio更新を行わない。"""

    risk_result = FakeRiskResult(
        allows_new_entries=False,
        is_blocked=True,
    )
    gate = FakeRiskAwareExecutionService(
        blocked=True,
    )
    (
        service,
        _queue,
        execution,
        portfolio,
        _prices,
        _clocks,
    ) = create_service(
        risk_aware_execution_service=gate,
        risk_result_provider=lambda: risk_result,
    )

    result = service.process(bars())

    assert result.is_completed
    assert result.signal_count == 1
    assert result.queued_count == 1
    assert execution.call_count == 0
    assert len(gate.calls) == 1
    assert portfolio.call_count == 0
    assert result.execution_count == 0
    assert result.risk_evaluated_count == 1
    assert result.risk_blocked_count == 1
    assert result.was_risk_blocked


def test_service_requires_risk_dependencies_together() -> None:
    """Risk GateとProviderの片方だけの設定を拒否する。"""

    gate = FakeRiskAwareExecutionService(
        blocked=False,
    )

    with pytest.raises(
        ValueError,
        match="risk_result_provider",
    ):
        create_service(
            risk_aware_execution_service=gate,
        )

    with pytest.raises(
        ValueError,
        match="risk_aware_execution_service",
    ):
        create_service(
            risk_result_provider=lambda: FakeRiskResult(
                allows_new_entries=True,
                is_blocked=False,
            ),
        )


def test_service_updates_market_price_before_order() -> None:
    """各足の価格更新後にその足のシグナルを処理する。"""

    (
        service,
        queue,
        _execution,
        _portfolio,
        updated_prices,
        _clocks,
    ) = create_service()

    service.process(bars())

    assert queue.signals
    assert updated_prices[-1] == ("7203", 1005.0)


def test_service_skips_duplicate_cycle() -> None:
    """同じ足を再投入しても注文を重複生成しない。"""

    (
        service,
        queue,
        execution,
        _portfolio,
        _prices,
        _clocks,
    ) = create_service()

    first = service.process(bars())
    second = service.process(bars())

    assert first.signal_count == 1
    assert second.signal_count == 0
    assert second.signal_result is not None
    assert second.signal_result.skipped_duplicate_count == 5
    assert len(queue.signals) == 1
    assert execution.call_count == 1


def test_service_processes_out_of_order_prices() -> None:
    """順不同の足を時系列順に処理する。"""

    (
        service,
        _queue,
        _execution,
        _portfolio,
        updated_prices,
        clocks,
    ) = create_service()

    result = service.process(
        tuple(reversed(bars()))
    )

    assert result.signal_count == 1
    assert updated_prices[-1] == ("7203", 1005.0)
    assert clocks == sorted(clocks)


def test_service_supports_custom_order_type() -> None:
    """注文タイプをキュー処理へ引き渡す。"""

    (
        service,
        queue,
        _execution,
        _portfolio,
        _prices,
        _clocks,
    ) = create_service()

    service.process(
        bars(),
        order_type=OrderType.MARKET,
    )

    assert queue.order_types == [OrderType.MARKET]


def test_service_rejects_invalid_equity_limit() -> None:
    """不正な資産曲線取得件数を拒否する。"""

    service, *_ = create_service()

    with pytest.raises(ValueError, match="取得件数"):
        service.process(
            bars(),
            equity_curve_limit=0,
        )


def test_service_raises_queue_failure_by_default() -> None:
    """既定ではキュー登録失敗を送出する。"""

    service, queue, *_ = create_service()
    queue.fail = True

    with pytest.raises(RuntimeError, match="queue failed"):
        service.process(bars())


def test_service_returns_failed_result_when_continuing() -> None:
    """継続モードでは例外を失敗結果へ変換する。"""

    service, queue, *_ = create_service()
    queue.fail = True

    result = service.process(
        bars(),
        continue_on_error=True,
    )

    assert result.status is RealtimePaperTradingStatus.COMPLETED
    assert result.signal_count == 1
    assert result.queue_results[0].is_failed


def test_service_returns_safe_empty_result() -> None:
    """空入力では全工程が空の正常結果になる。"""

    service, *_ = create_service()

    result = service.process(())

    assert result.is_completed
    assert result.signal_count == 0
    assert result.execution_count == 0
    assert result.portfolio_update_count == 0
    assert result.queue_results == ()
    assert result.risk_execution_results == ()


def test_service_diagnostics_record_signal_flow() -> None:
    """入力足からSignal Engineまでの処理件数を集計する。"""

    service, *_ = create_service()

    result = service.process(bars())

    assert result.is_completed

    snapshot = service.diagnostic_snapshot()
    assert snapshot.process_call_count == 1
    assert snapshot.input_bar_count == 5
    assert snapshot.signal_engine_call_count == 5
    assert snapshot.signal_processed_bar_count == 5
    assert snapshot.signal_skipped_duplicate_count == 0
    assert snapshot.signal_count == 1
    assert snapshot.queue_count == 1


def test_service_diagnostics_record_duplicate_bars() -> None:
    """重複足のスキップ件数を診断集計する。"""

    service, *_ = create_service()

    service.process(bars())
    service.process(bars())

    snapshot = service.diagnostic_snapshot()
    assert snapshot.process_call_count == 2
    assert snapshot.input_bar_count == 10
    assert snapshot.signal_engine_call_count == 10
    assert snapshot.signal_processed_bar_count == 5
    assert snapshot.signal_skipped_duplicate_count == 5
    assert snapshot.signal_count == 1


def test_service_diagnostics_record_failed_process() -> None:
    """処理例外を診断集計する。"""

    service, queue, *_ = create_service()
    queue.fail = True

    with pytest.raises(RuntimeError):
        service.process(bars())

    snapshot = service.diagnostic_snapshot()
    assert snapshot.failed_process_count == 1


def test_service_reset_diagnostics() -> None:
    """Paper Trading診断を初期化できる。"""

    service, *_ = create_service()
    service.process(())

    assert service.diagnostic_snapshot().process_call_count == 1

    service.reset_diagnostics()

    snapshot = service.diagnostic_snapshot()
    assert snapshot.process_call_count == 0
    assert snapshot.input_bar_count == 0



class FakeTraceRecorder:
    """Strategy RouteとSignalの記録順を保持する。"""

    def __init__(self) -> None:
        self.events = []

    def strategy_route_resolved(
        self,
        signal,
        *,
        decision,
        route,
    ) -> None:
        self.events.append(
            (
                "strategy_route_resolved",
                signal.code,
                decision.strategy_names,
                decision.routed,
                None if route is None else route.rating_tier,
            )
        )

    def signal_generated(
        self,
        signal,
        current_price,
    ) -> None:
        self.events.append(
            (
                "signal_generated",
                signal.code,
                signal.strategy_name,
            )
        )

    def queue_enqueued(
        self,
        signal,
        *,
        was_enqueued,
    ) -> None:
        self.events.append(
            (
                "queue_enqueued",
                signal.code,
                was_enqueued,
            )
        )

    def risk_evaluated(
        self,
        signal,
        decision,
    ) -> None:
        self.events.append(
            (
                "risk_evaluated",
                signal.code,
            )
        )

    def broker_result(
        self,
        signal,
        *,
        executed,
        saved_execution_count,
        blocked_reason=None,
    ) -> None:
        self.events.append(
            (
                "broker_result",
                signal.code,
                executed,
            )
        )


def test_service_traces_dynamic_strategy_route_before_signal() -> None:
    queue = FakeQueueService()
    execution = FakeExecutionService()
    portfolio = FakePortfolioService()
    trace = FakeTraceRecorder()
    routing_snapshot = StrategyRoutingSnapshot(
        generated_at=datetime(
            2026,
            7,
            17,
            8,
            20,
            tzinfo=JST,
        ),
        source_report_path="latest.json",
        route_count=1,
        routes=(
            SymbolStrategyRoute(
                code="7203",
                strategy_name="orb",
                rating_tier="B",
                total_score=57.4,
                strategy_score=6.78,
            ),
        ),
        fallback_strategy_names=(
            "orb",
            "pullback",
            "high-breakout",
        ),
    )
    signal_engine = RealtimeSignalEngine(
        enabled_strategy_names=(
            "orb",
            "pullback",
            "high-breakout",
        ),
        symbol_strategy_router=SymbolStrategyRouter(
            routing_snapshot
        ),
    )
    service = RealtimePaperTradingService(
        signal_engine=signal_engine,
        order_queue_service=queue,
        queue_execution_service=execution,
        portfolio_update_service=portfolio,
        market_price_updater=lambda _code, _price: None,
        trace_recorder=trace,
    )

    result = service.process(bars())

    assert result.signal_count == 1
    assert trace.events[0] == (
        "strategy_route_resolved",
        "7203",
        ("orb",),
        True,
        "B",
    )
    assert trace.events[1][0] == "signal_generated"
