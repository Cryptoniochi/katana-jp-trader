"""BacktestRunnerの統合テスト。"""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.backtest.backtest_portfolio_update_service import (
    BacktestPortfolioUpdateService,
)
from app.backtest.backtest_runner import (
    BacktestRunner,
    BacktestRunStatus,
)
from app.backtest.backtest_session import BacktestSession
from app.backtest.historical_models import (
    HistoricalBar,
    HistoricalBarSeries,
    MarketTimeframe,
)
from app.backtest.market_replay import MarketReplayEngine
from app.backtest.order_queue import BacktestOrderQueue
from app.backtest.order_queue_service import (
    BacktestOrderQueueService,
)
from app.backtest.queue_execution_service import (
    BacktestQueueExecutionService,
)
from app.backtest.strategy_runner import BacktestStrategyRunner
from app.database import initialize_database
from app.trading.equity_curve_service import EquityCurveService
from app.trading.order_broker_sync_service import (
    OrderBrokerSyncService,
)
from app.trading.order_repository import OrderRepository
from app.trading.order_service import SignalOrderService
from app.trading.paper_broker import (
    PaperBroker,
    PaperBrokerSettings,
)
from app.trading.portfolio_repository import PortfolioRepository
from app.trading.portfolio_service import PortfolioService
from app.trading.position_repository import PositionRepository
from app.trading.position_service import PositionService
from app.trading.signal_models import (
    SignalAction,
    TradeSignal,
)
from app.trading.signal_repository import SignalRepository
from app.trading.trade_execution_repository import (
    TradeExecutionRepository,
)


BASE_TIME = datetime(
    2026,
    7,
    1,
    0,
    0,
    tzinfo=timezone.utc,
)


class MutableClock:
    """任意日時を返すテスト用時計。"""

    def __init__(self, current: datetime) -> None:
        self.current = current

    def now(self) -> datetime:
        return self.current


class OneBuySignalStrategy:
    """最初のFrameでBUYシグナルを1件生成する。"""

    strategy_name = "one-buy"

    def evaluate(self, frame) -> tuple[TradeSignal, ...]:
        if not frame.is_first:
            return ()

        return (
            TradeSignal(
                signal_id="signal-buy-001",
                code=frame.code,
                strategy_name=self.strategy_name,
                action=SignalAction.BUY,
                generated_at=frame.replayed_at,
                signal_price=frame.current_bar.close_price,
                quantity=100,
                reason="first frame buy",
            ),
        )


class FailingStrategy:
    """戦略評価時に失敗する。"""

    strategy_name = "failing"

    def evaluate(self, frame) -> tuple[TradeSignal, ...]:
        raise RuntimeError("strategy failed")


def create_series() -> HistoricalBarSeries:
    """2本の5分足系列を作成する。"""

    bars = tuple(
        HistoricalBar(
            code="7203",
            timeframe=MarketTimeframe.MINUTE_5,
            opened_at=(
                BASE_TIME
                + timedelta(minutes=index * 5)
            ),
            open_price=2500.0,
            high_price=2520.0,
            low_price=2490.0,
            close_price=2500.0,
            volume=1000.0,
        )
        for index in range(2)
    )

    return HistoricalBarSeries(
        code="7203",
        timeframe=MarketTimeframe.MINUTE_5,
        bars=bars,
    )


def create_runner(
    tmp_path: Path,
    *,
    strategy=None,
    initial_cash: float = 1_000_000.0,
) -> tuple[
    BacktestRunner,
    SignalRepository,
    OrderRepository,
    TradeExecutionRepository,
    PositionRepository,
    PortfolioRepository,
]:
    """実SQLiteを使う統合Runnerを作成する。"""

    database_path = tmp_path / "katana.db"
    initialize_database(database_path)

    clock = MutableClock(
        BASE_TIME + timedelta(minutes=10)
    )

    signal_repository = SignalRepository(
        database_path,
        now_provider=clock.now,
    )
    order_repository = OrderRepository(
        database_path,
        now_provider=clock.now,
    )
    execution_repository = TradeExecutionRepository(
        database_path,
        now_provider=clock.now,
    )
    position_repository = PositionRepository(
        database_path,
        now_provider=clock.now,
    )
    portfolio_repository = PortfolioRepository(
        database_path,
        now_provider=clock.now,
    )

    resolved_strategy = (
        strategy
        if strategy is not None
        else OneBuySignalStrategy()
    )

    session = BacktestSession(
        session_id="session-001",
        strategy_runner=BacktestStrategyRunner(
            replay_engine=MarketReplayEngine(
                create_series()
            ),
            strategy=resolved_strategy,
        ),
        now_provider=clock.now,
    )

    order_queue = BacktestOrderQueue()
    signal_order_service = SignalOrderService(
        signal_repository=signal_repository,
        order_repository=order_repository,
    )
    queue_service = BacktestOrderQueueService(
        signal_repository=signal_repository,
        order_service=signal_order_service,
        order_queue=order_queue,
        now_provider=clock.now,
    )

    broker = PaperBroker(
        price_provider=lambda _code: 2500.0,
        settings=PaperBrokerSettings(
            initial_cash=initial_cash,
        ),
        now_provider=clock.now,
    )

    broker_sync_service = OrderBrokerSyncService(
        order_repository=order_repository,
        broker=broker,
    )
    queue_execution_service = (
        BacktestQueueExecutionService(
            order_queue=order_queue,
            broker_sync_service=broker_sync_service,
            execution_repository=execution_repository,
            broker_name=broker.broker_name,
        )
    )

    position_service = PositionService(
        database_path=database_path,
        position_repository=position_repository,
    )
    portfolio_service = PortfolioService(
        position_repository=position_repository,
        broker=broker,
    )
    equity_curve_service = EquityCurveService(
        portfolio_repository=portfolio_repository,
    )
    portfolio_update_service = (
        BacktestPortfolioUpdateService(
            position_service=position_service,
            portfolio_service=portfolio_service,
            portfolio_repository=portfolio_repository,
            equity_curve_service=equity_curve_service,
        )
    )

    runner = BacktestRunner(
        session=session,
        order_queue_service=queue_service,
        queue_execution_service=queue_execution_service,
        portfolio_update_service=portfolio_update_service,
    )

    return (
        runner,
        signal_repository,
        order_repository,
        execution_repository,
        position_repository,
        portfolio_repository,
    )


def test_runner_completes_full_pipeline(
    tmp_path: Path,
) -> None:
    """戦略実行から資産曲線までを完走する。"""

    (
        runner,
        signal_repository,
        order_repository,
        execution_repository,
        position_repository,
        portfolio_repository,
    ) = create_runner(tmp_path)

    result = runner.run()

    assert result.status is BacktestRunStatus.COMPLETED
    assert result.is_completed
    assert not result.is_failed
    assert result.frame_count == 2
    assert result.signal_count == 1
    assert result.queued_count == 1
    assert result.existing_order_count == 0
    assert result.queue_failure_count == 0
    assert result.execution_count == 1
    assert result.execution_failure_count == 0
    assert result.portfolio_update_count == 1

    assert signal_repository.count() == 1
    assert order_repository.count() == 1
    assert execution_repository.count() == 1
    assert position_repository.count() == 1
    assert portfolio_repository.count() == 1

    report = result.equity_curve_report

    assert report is not None
    assert report.point_count == 1
    assert report.final_equity == pytest.approx(
        1_000_000.0
    )


def test_runner_completes_without_signals(
    tmp_path: Path,
) -> None:
    """シグナルがなくても正常完了する。"""

    class NoSignalStrategy:
        strategy_name = "no-signal"

        def evaluate(
            self,
            frame,
        ) -> tuple[TradeSignal, ...]:
            return ()

    (
        runner,
        _signal_repository,
        _order_repository,
        _execution_repository,
        _position_repository,
        _portfolio_repository,
    ) = create_runner(
        tmp_path,
        strategy=NoSignalStrategy(),
    )

    result = runner.run()

    assert result.is_completed
    assert result.frame_count == 2
    assert result.signal_count == 0
    assert result.queued_count == 0
    assert result.execution_count == 0
    assert result.portfolio_update_count == 0
    assert result.equity_curve_report is None


def test_runner_returns_failed_result_when_enabled(
    tmp_path: Path,
) -> None:
    """継続設定時は例外を失敗結果へ変換する。"""

    (
        runner,
        _signal_repository,
        _order_repository,
        _execution_repository,
        _position_repository,
        _portfolio_repository,
    ) = create_runner(
        tmp_path,
        strategy=FailingStrategy(),
    )

    result = runner.run(
        continue_on_error=True
    )

    assert result.status is BacktestRunStatus.FAILED
    assert result.is_failed
    assert not result.is_completed
    assert result.error_message == "strategy failed"


def test_runner_reraises_when_continuation_disabled(
    tmp_path: Path,
) -> None:
    """継続無効時は例外を再送出する。"""

    (
        runner,
        _signal_repository,
        _order_repository,
        _execution_repository,
        _position_repository,
        _portfolio_repository,
    ) = create_runner(
        tmp_path,
        strategy=FailingStrategy(),
    )

    with pytest.raises(
        RuntimeError,
        match="strategy failed",
    ):
        runner.run(
            continue_on_error=False
        )


def test_runner_rejects_invalid_equity_curve_limit(
    tmp_path: Path,
) -> None:
    """0以下の資産曲線取得件数を拒否する。"""

    (
        runner,
        _signal_repository,
        _order_repository,
        _execution_repository,
        _position_repository,
        _portfolio_repository,
    ) = create_runner(tmp_path)

    with pytest.raises(ValueError, match="取得件数"):
        runner.run(
            equity_curve_limit=0
        )
