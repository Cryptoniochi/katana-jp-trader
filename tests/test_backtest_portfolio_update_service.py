"""BacktestPortfolioUpdateServiceの統合テスト。"""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.backtest.backtest_portfolio_update_service import (
    BacktestPortfolioUpdateService,
)
from app.database import initialize_database
from app.trading.equity_curve_service import EquityCurveService
from app.trading.order_models import OrderSide
from app.trading.paper_broker import (
    PaperBroker,
    PaperBrokerSettings,
)
from app.trading.portfolio_repository import PortfolioRepository
from app.trading.portfolio_service import PortfolioService
from app.trading.position_repository import PositionRepository
from app.trading.position_service import PositionService
from app.trading.trade_execution_models import (
    TradeExecution,
    TradeExecutionRecord,
)


BASE_TIME = datetime(
    2026,
    7,
    1,
    0,
    30,
    tzinfo=timezone.utc,
)


class MutableClock:
    """任意時点へ進められる時計。"""

    def __init__(self, current: datetime) -> None:
        self.current = current

    def now(self) -> datetime:
        return self.current


def create_execution_record(
    *,
    record_id: int,
    execution_id: str,
    side: OrderSide,
    quantity: int,
    price: float,
    executed_at: datetime,
) -> TradeExecutionRecord:
    """テスト用約定レコードを作成する。"""

    return TradeExecutionRecord(
        id=record_id,
        execution=TradeExecution(
            execution_id=execution_id,
            signal_id=f"signal-{execution_id}",
            order_id=f"order-{execution_id}",
            broker_order_id=f"broker-{execution_id}",
            code="7203",
            side=side,
            quantity=quantity,
            execution_price=price,
            executed_at=executed_at,
            broker_name="paper",
        ),
        created_at=executed_at,
        updated_at=executed_at,
    )


def create_environment(
    tmp_path: Path,
) -> tuple[
    MutableClock,
    PaperBroker,
    PositionRepository,
    PortfolioRepository,
    BacktestPortfolioUpdateService,
]:
    """実SQLiteとPaperBrokerを使う統合環境を作成する。"""

    database_path = tmp_path / "katana.db"
    initialize_database(database_path)

    clock = MutableClock(BASE_TIME)

    broker = PaperBroker(
        price_provider=lambda _code: 2500.0,
        settings=PaperBrokerSettings(
            initial_cash=1_000_000.0,
        ),
        now_provider=clock.now,
    )

    position_repository = PositionRepository(
        database_path,
        now_provider=clock.now,
    )
    position_service = PositionService(
        database_path=database_path,
        position_repository=position_repository,
    )

    portfolio_repository = PortfolioRepository(
        database_path,
        now_provider=clock.now,
    )
    portfolio_service = PortfolioService(
        position_repository=position_repository,
        broker=broker,
    )
    equity_curve_service = EquityCurveService(
        portfolio_repository=portfolio_repository
    )

    service = BacktestPortfolioUpdateService(
        position_service=position_service,
        portfolio_service=portfolio_service,
        portfolio_repository=portfolio_repository,
        equity_curve_service=equity_curve_service,
    )

    return (
        clock,
        broker,
        position_repository,
        portfolio_repository,
        service,
    )


def submit_broker_order(
    *,
    broker: PaperBroker,
    execution_record: TradeExecutionRecord,
) -> None:
    """約定内容と同じ取引をPaperBrokerへ反映する。"""

    from app.trading.order_models import (
        OrderType,
        TradeOrder,
    )

    execution = execution_record.execution

    broker.submit_order(
        TradeOrder(
            order_id=execution.order_id,
            signal_id=execution.signal_id,
            code=execution.code,
            side=execution.side,
            order_type=OrderType.MARKET,
            quantity=execution.quantity,
        )
    )


def test_service_applies_buy_and_saves_portfolio(
    tmp_path: Path,
) -> None:
    """買い約定をポジション・履歴・資産曲線へ反映する。"""

    (
        _clock,
        broker,
        position_repository,
        portfolio_repository,
        service,
    ) = create_environment(tmp_path)

    execution = create_execution_record(
        record_id=1,
        execution_id="execution-buy",
        side=OrderSide.BUY,
        quantity=100,
        price=2500.0,
        executed_at=BASE_TIME,
    )

    submit_broker_order(
        broker=broker,
        execution_record=execution,
    )

    result = service.apply_execution(execution)

    assert result.position_was_applied
    assert not result.position_closed
    assert position_repository.count() == 1
    assert portfolio_repository.count() == 1

    snapshot = result.portfolio_snapshot

    assert snapshot.position_count == 1
    assert snapshot.cash_balance == pytest.approx(
        750_000.0
    )
    assert snapshot.total_market_value == pytest.approx(
        250_000.0
    )
    assert snapshot.broker_equity == pytest.approx(
        1_000_000.0
    )

    report = result.equity_curve_report

    assert report.point_count == 1
    assert report.initial_equity == pytest.approx(
        1_000_000.0
    )
    assert report.final_equity == pytest.approx(
        1_000_000.0
    )


def test_service_updates_equity_curve_across_executions(
    tmp_path: Path,
) -> None:
    """約定ごとにポートフォリオ履歴と資産曲線を更新する。"""

    (
        clock,
        broker,
        position_repository,
        portfolio_repository,
        service,
    ) = create_environment(tmp_path)

    buy = create_execution_record(
        record_id=1,
        execution_id="execution-buy",
        side=OrderSide.BUY,
        quantity=100,
        price=2500.0,
        executed_at=BASE_TIME,
    )

    submit_broker_order(
        broker=broker,
        execution_record=buy,
    )
    first = service.apply_execution(buy)

    second_time = BASE_TIME + timedelta(minutes=5)
    clock.current = second_time
    broker.update_market_price(
        "7203",
        2600.0,
    )

    sell = create_execution_record(
        record_id=2,
        execution_id="execution-sell",
        side=OrderSide.SELL,
        quantity=100,
        price=2500.0,
        executed_at=second_time,
    )

    submit_broker_order(
        broker=broker,
        execution_record=sell,
    )
    second = service.apply_execution(sell)

    assert first.position_was_applied
    assert second.position_was_applied
    assert second.position_closed
    assert position_repository.count() == 0
    assert portfolio_repository.count() == 2
    assert second.equity_curve_report.point_count == 2
    assert second.equity_curve_report.final_equity == pytest.approx(
        1_000_000.0
    )

def test_service_is_idempotent_for_position_application(
    tmp_path: Path,
) -> None:
    """同じ約定のポジション反映は二重実行しない。"""

    (
        _clock,
        broker,
        position_repository,
        _portfolio_repository,
        service,
    ) = create_environment(tmp_path)

    execution = create_execution_record(
        record_id=1,
        execution_id="execution-buy",
        side=OrderSide.BUY,
        quantity=100,
        price=2500.0,
        executed_at=BASE_TIME,
    )

    submit_broker_order(
        broker=broker,
        execution_record=execution,
    )

    first = service.apply_execution(execution)

    assert first.position_was_applied
    assert position_repository.list_recent()[0].quantity == 100


def test_service_rejects_invalid_equity_curve_limit(
    tmp_path: Path,
) -> None:
    """0以下の履歴取得件数を拒否する。"""

    (
        _clock,
        _broker,
        _position_repository,
        _portfolio_repository,
        service,
    ) = create_environment(tmp_path)

    execution = create_execution_record(
        record_id=1,
        execution_id="execution-buy",
        side=OrderSide.BUY,
        quantity=100,
        price=2500.0,
        executed_at=BASE_TIME,
    )

    with pytest.raises(ValueError, match="取得件数"):
        service.apply_execution(
            execution,
            equity_curve_limit=0,
        )

    with pytest.raises(ValueError, match="取得件数"):
        service.apply_executions(
            (),
            equity_curve_limit=0,
        )


def test_service_returns_empty_batch_result(
    tmp_path: Path,
) -> None:
    """約定がなければ空の結果を返す。"""

    (
        _clock,
        _broker,
        _position_repository,
        _portfolio_repository,
        service,
    ) = create_environment(tmp_path)

    result = service.apply_executions(())

    assert result.items == ()
    assert result.processed_count == 0
    assert result.applied_count == 0
    assert result.latest_snapshot is None
    assert result.latest_equity_curve is None
