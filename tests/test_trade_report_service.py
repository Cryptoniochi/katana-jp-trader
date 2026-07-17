"""TradeReportServiceのテスト。"""

from datetime import datetime, timedelta, timezone

import pytest

from app.backtest.trade_report_service import (
    TradeReportService,
)
from app.trading.order_models import OrderSide
from app.trading.signal_models import (
    SignalAction,
    SignalStatus,
    TradeSignal,
    TradeSignalRecord,
)
from app.trading.trade_execution_models import (
    TradeExecution,
    TradeExecutionRecord,
)


BASE_TIME = datetime(
    2026,
    7,
    1,
    0,
    20,
    tzinfo=timezone.utc,
)


def execution_record(
    *,
    record_id: int,
    execution_id: str,
    signal_id: str,
    side: OrderSide,
    quantity: int,
    price: float,
    minute: int,
    code: str = "7203",
    commission: float = 0.0,
    slippage: float = 0.0,
) -> TradeExecutionRecord:
    """テスト用約定履歴を作成する。"""

    executed_at = BASE_TIME + timedelta(
        minutes=minute
    )

    return TradeExecutionRecord(
        id=record_id,
        execution=TradeExecution(
            execution_id=execution_id,
            signal_id=signal_id,
            order_id=f"order-{execution_id}",
            broker_order_id=f"broker-{execution_id}",
            code=code,
            side=side,
            quantity=quantity,
            execution_price=price,
            executed_at=executed_at,
            broker_name="paper",
            commission=commission,
            slippage=slippage,
        ),
        created_at=executed_at,
        updated_at=executed_at,
    )


class FakeExecutionRepository:
    """固定約定履歴を新しい順に返す。"""

    def __init__(
        self,
        records: list[TradeExecutionRecord],
    ) -> None:
        self.records = records
        self.requested_limit: int | None = None
        self.requested_code: str | None = None

    def list_recent(
        self,
        *,
        limit: int = 100,
        code: str | None = None,
        side=None,
        order_id=None,
        signal_id=None,
    ) -> list[TradeExecutionRecord]:
        self.requested_limit = limit
        self.requested_code = code

        filtered = [
            record
            for record in self.records
            if code is None or record.code == code
        ]

        return sorted(
            filtered,
            key=lambda record: record.execution.executed_at,
            reverse=True,
        )[:limit]


class FakeSignalRepository:
    """固定シグナルを返す。"""

    def __init__(
        self,
        records: dict[str, TradeSignalRecord],
    ) -> None:
        self.records = records

    def get(
        self,
        signal_id: str,
    ) -> TradeSignalRecord:
        return self.records[signal_id]


def signal_record(
    *,
    record_id: int,
    signal_id: str,
    action: SignalAction,
    exit_reason: str | None = None,
) -> TradeSignalRecord:
    """テスト用保存済みシグナルを作成する。"""

    metadata = {}

    if exit_reason is not None:
        metadata["exit_reason"] = exit_reason

    signal = TradeSignal(
        signal_id=signal_id,
        code="7203",
        strategy_name="orb",
        action=action,
        generated_at=BASE_TIME,
        signal_price=1000.0,
        quantity=100,
        reason="test",
        metadata=metadata,
    )

    return TradeSignalRecord(
        id=record_id,
        signal=signal,
        status=SignalStatus.PROCESSED,
        processed_at=BASE_TIME,
        process_note="processed",
        created_at=BASE_TIME,
        updated_at=BASE_TIME,
    )


def test_service_pairs_buy_and_sell() -> None:
    """BUYとSELLを完結トレードへ変換する。"""

    buy = execution_record(
        record_id=1,
        execution_id="buy-1",
        signal_id="signal-buy",
        side=OrderSide.BUY,
        quantity=100,
        price=1000.0,
        minute=0,
        commission=50.0,
        slippage=10.0,
    )
    sell = execution_record(
        record_id=2,
        execution_id="sell-1",
        signal_id="signal-exit",
        side=OrderSide.SELL,
        quantity=100,
        price=1020.0,
        minute=10,
        commission=50.0,
        slippage=10.0,
    )
    signals = FakeSignalRepository(
        {
            "signal-exit": signal_record(
                record_id=2,
                signal_id="signal-exit",
                action=SignalAction.EXIT,
                exit_reason="take_profit",
            )
        }
    )

    report = TradeReportService(
        execution_repository=(
            FakeExecutionRepository([sell, buy])
        ),
        signal_repository=signals,
    ).create_report()

    assert report.trade_count == 1
    assert report.unmatched_buy_quantity == 0
    assert report.unmatched_sell_quantity == 0

    trade = report.trades[0]

    assert trade.quantity == 100
    assert trade.entry_price == pytest.approx(1000.0)
    assert trade.exit_price == pytest.approx(1020.0)
    assert trade.gross_profit_loss == pytest.approx(2000.0)
    assert trade.total_cost == pytest.approx(120.0)
    assert trade.net_profit_loss == pytest.approx(1880.0)
    assert trade.return_rate == pytest.approx(0.0188)
    assert trade.holding_seconds == pytest.approx(600.0)
    assert trade.exit_reason == "take_profit"
    assert trade.is_winner


def test_service_uses_fifo_for_multiple_buy_lots() -> None:
    """複数BUYをFIFOで部分決済する。"""

    records = [
        execution_record(
            record_id=1,
            execution_id="buy-1",
            signal_id="signal-buy-1",
            side=OrderSide.BUY,
            quantity=100,
            price=1000.0,
            minute=0,
        ),
        execution_record(
            record_id=2,
            execution_id="buy-2",
            signal_id="signal-buy-2",
            side=OrderSide.BUY,
            quantity=100,
            price=1100.0,
            minute=5,
        ),
        execution_record(
            record_id=3,
            execution_id="sell-1",
            signal_id="signal-sell-1",
            side=OrderSide.SELL,
            quantity=150,
            price=1200.0,
            minute=10,
        ),
    ]

    report = TradeReportService(
        execution_repository=(
            FakeExecutionRepository(records)
        )
    ).create_report()

    assert report.trade_count == 2
    assert [
        trade.quantity
        for trade in report.trades
    ] == [100, 50]
    assert [
        trade.entry_price
        for trade in report.trades
    ] == [1000.0, 1100.0]
    assert report.unmatched_buy_quantity == 50
    assert report.unmatched_sell_quantity == 0


def test_service_tracks_unmatched_sell_quantity() -> None:
    """保有数量を超えるSELLを未対応数量として残す。"""

    records = [
        execution_record(
            record_id=1,
            execution_id="buy-1",
            signal_id="signal-buy-1",
            side=OrderSide.BUY,
            quantity=50,
            price=1000.0,
            minute=0,
        ),
        execution_record(
            record_id=2,
            execution_id="sell-1",
            signal_id="signal-sell-1",
            side=OrderSide.SELL,
            quantity=100,
            price=900.0,
            minute=5,
        ),
    ]

    report = TradeReportService(
        execution_repository=(
            FakeExecutionRepository(records)
        )
    ).create_report()

    assert report.trade_count == 1
    assert report.unmatched_sell_quantity == 50
    assert report.trades[0].is_loser


def test_service_separates_codes() -> None:
    """異なる銘柄の約定を対応付けない。"""

    records = [
        execution_record(
            record_id=1,
            execution_id="buy-7203",
            signal_id="signal-buy-7203",
            side=OrderSide.BUY,
            quantity=100,
            price=1000.0,
            minute=0,
            code="7203",
        ),
        execution_record(
            record_id=2,
            execution_id="sell-8306",
            signal_id="signal-sell-8306",
            side=OrderSide.SELL,
            quantity=100,
            price=1000.0,
            minute=5,
            code="8306",
        ),
    ]

    report = TradeReportService(
        execution_repository=(
            FakeExecutionRepository(records)
        )
    ).create_report()

    assert report.trade_count == 0
    assert report.unmatched_buy_quantity == 100
    assert report.unmatched_sell_quantity == 100


def test_service_passes_limit_and_code() -> None:
    """取得条件をRepositoryへ渡す。"""

    repository = FakeExecutionRepository([])

    TradeReportService(
        execution_repository=repository
    ).create_report(
        limit=25,
        code="7203",
    )

    assert repository.requested_limit == 25
    assert repository.requested_code == "7203"


def test_service_rejects_invalid_limit() -> None:
    """0以下の取得件数を拒否する。"""

    service = TradeReportService(
        execution_repository=(
            FakeExecutionRepository([])
        )
    )

    with pytest.raises(ValueError, match="取得件数"):
        service.create_report(limit=0)


def test_empty_report_has_zero_totals() -> None:
    """約定がなければ空レポートを返す。"""

    report = TradeReportService(
        execution_repository=(
            FakeExecutionRepository([])
        )
    ).create_report()

    assert report.trades == ()
    assert report.trade_count == 0
    assert report.total_net_profit_loss == 0.0
    assert report.winning_trade_count == 0
    assert report.losing_trade_count == 0
    assert report.flat_trade_count == 0
