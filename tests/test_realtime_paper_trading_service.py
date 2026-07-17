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
from app.market.models import StockPrice
from app.market.realtime_paper_trading_service import (
    RealtimePaperTradingService,
    RealtimePaperTradingStatus,
)
from app.market.realtime_signal_engine import (
    RealtimeSignalEngine,
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


def create_service():
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
        portfolio,
        updated_prices,
        clocks,
    ) = create_service()

    result = service.process(bars())

    assert result.is_completed
    assert result.signal_count == 1
    assert result.queued_count == 1
    assert queue.signals[0].action is SignalAction.BUY
    assert execution.call_count == 1
    assert portfolio.call_count == 1
    assert len(updated_prices) == 5
    assert len(clocks) == 5


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
        portfolio,
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
    assert portfolio.call_count == 1


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
