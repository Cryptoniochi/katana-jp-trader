"""ORBからPaper Broker約定までのEnd-to-End統合テスト。"""

import csv
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.database import initialize_database
from app.market.models import StockPrice
from app.strategy.opening_range_breakout import (
    OpeningRangeBreakoutStrategy,
)
from app.strategy.orb_diagnostics import (
    OrbDiagnosticService,
)
from app.trading.execution_engine import (
    ExecutionDecision,
    ExecutionEngine,
)
from app.trading.execution_report import (
    ExecutionReportService,
)
from app.trading.execution_risk import (
    ExecutionRiskPolicy,
    ExecutionRiskReason,
    ExecutionRiskService,
)
from app.trading.order_broker_sync_service import (
    OrderBrokerSyncService,
)
from app.trading.order_models import (
    OrderStatus,
    OrderType,
)
from app.trading.order_repository import (
    OrderRepository,
)
from app.trading.order_service import (
    SignalOrderService,
)
from app.trading.orb_signal_factory import (
    OrbSignalFactory,
    OrbSignalFactorySettings,
)
from app.trading.orb_signal_service import (
    OrbSignalGenerationService,
)
from app.trading.paper_broker import (
    PaperBroker,
    PaperBrokerSettings,
)
from app.trading.paper_trading_pipeline import (
    PaperTradingPipeline,
)
from app.trading.signal_models import (
    SignalStatus,
)
from app.trading.signal_repository import (
    SignalRepository,
)


CURRENT_TIME = datetime(
    2026,
    7,
    16,
    1,
    0,
    tzinfo=timezone.utc,
)


def create_price(
    time_text: str,
    *,
    code: str = "7203",
    high: float,
    low: float,
    close: float,
    volume: int,
) -> StockPrice:
    """統合テスト用の5分足を作成する。"""

    return StockPrice(
        code=code,
        datetime=datetime.strptime(
            f"2026-07-16 {time_text}",
            "%Y-%m-%d %H:%M",
        ),
        open=close,
        high=high,
        low=low,
        close=close,
        volume=volume,
    )


def create_candidate_prices(
    *,
    code: str = "7203",
) -> list[StockPrice]:
    """ORB取引候補になる5分足を作成する。"""

    return [
        create_price(
            "09:00",
            code=code,
            high=1005.0,
            low=995.0,
            close=1000.0,
            volume=100_000,
        ),
        create_price(
            "09:15",
            code=code,
            high=1010.0,
            low=998.0,
            close=1005.0,
            volume=100_000,
        ),
        create_price(
            "09:20",
            code=code,
            high=1020.0,
            low=1008.0,
            close=1015.0,
            volume=200_000,
        ),
        create_price(
            "14:50",
            code=code,
            high=1025.0,
            low=1010.0,
            close=1020.0,
            volume=300_000,
        ),
    ]


def create_rejected_prices() -> list[StockPrice]:
    """ORB価格ブレイクが発生しない5分足を作成する。"""

    return [
        create_price(
            "09:00",
            high=1005.0,
            low=995.0,
            close=1000.0,
            volume=100_000,
        ),
        create_price(
            "09:15",
            high=1010.0,
            low=998.0,
            close=1005.0,
            volume=100_000,
        ),
        create_price(
            "09:20",
            high=1010.0,
            low=1000.0,
            close=1008.0,
            volume=200_000,
        ),
        create_price(
            "14:50",
            high=1009.0,
            low=1000.0,
            close=1005.0,
            volume=300_000,
        ),
    ]


def create_strategy() -> OpeningRangeBreakoutStrategy:
    """統合テスト用ORB戦略を作成する。"""

    return OpeningRangeBreakoutStrategy(
        quantity=100,
        min_opening_range_volume=200_000,
        min_breakout_volume=150_000,
        breakout_volume_ratio=1.2,
        min_price=500.0,
        max_price=20_000.0,
        min_opening_range_turnover=(
            100_000_000.0
        ),
        min_breakout_turnover=(
            100_000_000.0
        ),
    )


def create_environment(
    tmp_path: Path,
    *,
    initial_cash: float = 1_000_000.0,
    market_price: float = 1020.0,
    risk_policy: ExecutionRiskPolicy | None = None,
) -> tuple[
    SignalRepository,
    OrderRepository,
    PaperBroker,
    PaperTradingPipeline,
]:
    """実SQLiteを使用する統合環境を作成する。"""

    database_path = tmp_path / "katana.db"

    initialize_database(
        database_path
    )

    signal_repository = SignalRepository(
        database_path,
        now_provider=lambda: CURRENT_TIME,
    )

    order_repository = OrderRepository(
        database_path,
        now_provider=lambda: CURRENT_TIME,
    )

    broker = PaperBroker(
        settings=PaperBrokerSettings(
            initial_cash=initial_cash,
        ),
        price_provider=lambda _code: market_price,
        now_provider=lambda: CURRENT_TIME,
    )

    signal_generation_service = (
        OrbSignalGenerationService(
            diagnostic_service=(
                OrbDiagnosticService(
                    create_strategy()
                )
            ),
            signal_factory=(
                OrbSignalFactory(
                    settings=(
                        OrbSignalFactorySettings(
                            strategy_name="orb",
                            quantity=100,
                            confidence=0.8,
                        )
                    )
                )
            ),
            signal_repository=signal_repository,
        )
    )

    order_service = SignalOrderService(
        signal_repository=signal_repository,
        order_repository=order_repository,
    )

    broker_sync_service = (
        OrderBrokerSyncService(
            order_repository=order_repository,
            broker=broker,
        )
    )

    execution_engine = ExecutionEngine(
        signal_repository=signal_repository,
        order_service=order_service,
        broker_sync_service=broker_sync_service,
    )

    risk_service = ExecutionRiskService(
        broker=broker,
        policy=(
            risk_policy
            if risk_policy is not None
            else ExecutionRiskPolicy(
                max_order_value=500_000.0,
                minimum_cash_reserve=100_000.0,
                max_position_count=5,
                max_code_market_value=500_000.0,
                max_total_market_value=1_000_000.0,
                allow_additional_buy=False,
            )
        ),
    )

    pipeline = PaperTradingPipeline(
        signal_generation_service=(
            signal_generation_service
        ),
        risk_service=risk_service,
        execution_engine=execution_engine,
        signal_repository=signal_repository,
        report_service=ExecutionReportService(),
    )

    return (
        signal_repository,
        order_repository,
        broker,
        pipeline,
    )


def test_pipeline_executes_orb_candidate_end_to_end(
    tmp_path: Path,
) -> None:
    """ORB候補をシグナル・注文・約定まで一気通しする。"""

    (
        signal_repository,
        order_repository,
        broker,
        pipeline,
    ) = create_environment(
        tmp_path
    )

    result = pipeline.run(
        create_candidate_prices(),
        report_generated_at=CURRENT_TIME,
    )

    assert result.generated_signal_count == 1
    assert result.saved_signal_count == 1
    assert result.duplicate_signal_count == 0

    assert result.approved_count == 1
    assert result.rejected_count == 0
    assert result.risk_failed_count == 0

    assert result.executed_count == 1
    assert result.failed_count == 0
    assert result.is_successful is True

    assert signal_repository.count(
        status=SignalStatus.PROCESSED,
    ) == 1

    assert order_repository.count(
        status=OrderStatus.FILLED,
    ) == 1

    order = order_repository.list_recent()[0]

    assert order.code == "7203"
    assert order.filled_quantity == 100
    assert order.average_fill_price == pytest.approx(
        1020.0
    )
    assert order.broker_order_id == (
        "paper-order-00000001"
    )

    positions = broker.list_positions()

    assert len(positions) == 1
    assert positions[0].code == "7203"
    assert positions[0].quantity == 100

    report = result.execution_report

    assert report.input_count == 1
    assert report.filled_count == 1
    assert report.failed_count == 0
    assert report.rows[0].code == "7203"


def test_pipeline_rejects_signal_by_risk_policy(
    tmp_path: Path,
) -> None:
    """最大注文金額超過時は注文を作らずシグナルを取消す。"""

    (
        signal_repository,
        order_repository,
        broker,
        pipeline,
    ) = create_environment(
        tmp_path,
        risk_policy=ExecutionRiskPolicy(
            max_order_value=50_000.0,
            minimum_cash_reserve=0.0,
            max_position_count=5,
            max_code_market_value=500_000.0,
            max_total_market_value=1_000_000.0,
        ),
    )

    result = pipeline.run(
        create_candidate_prices(),
        report_generated_at=CURRENT_TIME,
    )

    assert result.saved_signal_count == 1
    assert result.approved_count == 0
    assert result.rejected_count == 1
    assert result.executed_count == 0
    assert result.failed_count == 1
    assert result.is_successful is False

    assert (
        ExecutionRiskReason.ORDER_VALUE_LIMIT
        in result.risk_results[0].reasons
    )

    assert signal_repository.count(
        status=SignalStatus.CANCELLED,
    ) == 1

    assert order_repository.count() == 0
    assert broker.list_orders() == []
    assert broker.list_positions() == []

    item = result.execution_batch_result.items[0]

    assert item.decision is (
        ExecutionDecision.FAILED
    )
    assert "order_value_limit" in (
        item.message or ""
    )


def test_pipeline_does_nothing_without_orb_candidate(
    tmp_path: Path,
) -> None:
    """ORB候補がなければシグナルも注文も作らない。"""

    (
        signal_repository,
        order_repository,
        broker,
        pipeline,
    ) = create_environment(
        tmp_path
    )

    result = pipeline.run(
        create_rejected_prices(),
        report_generated_at=CURRENT_TIME,
    )

    assert result.generated_signal_count == 0
    assert result.saved_signal_count == 0
    assert result.approved_count == 0
    assert result.executed_count == 0
    assert result.failed_count == 0
    assert result.is_successful is True

    assert signal_repository.count() == 0
    assert order_repository.count() == 0
    assert broker.list_orders() == []

    assert result.execution_report.input_count == 0
    assert result.execution_report.is_successful is True


def test_pipeline_is_idempotent_on_same_market_data(
    tmp_path: Path,
) -> None:
    """同じ5分足を再実行しても二重発注しない。"""

    (
        signal_repository,
        order_repository,
        broker,
        pipeline,
    ) = create_environment(
        tmp_path
    )

    prices = create_candidate_prices()

    first = pipeline.run(
        prices,
        report_generated_at=CURRENT_TIME,
    )

    second = pipeline.run(
        prices,
        report_generated_at=CURRENT_TIME,
    )

    assert first.saved_signal_count == 1
    assert first.executed_count == 1

    assert second.generated_signal_count == 1
    assert second.saved_signal_count == 0
    assert second.duplicate_signal_count == 1
    assert second.executed_count == 0
    assert second.failed_count == 0

    assert signal_repository.count() == 1
    assert order_repository.count() == 1
    assert len(broker.list_orders()) == 1
    assert broker.list_positions()[0].quantity == 100


def test_pipeline_creates_active_limit_order(
    tmp_path: Path,
) -> None:
    """条件未到達の指値注文をSENT状態で保持する。"""

    (
        _signal_repository,
        order_repository,
        broker,
        pipeline,
    ) = create_environment(
        tmp_path,
        market_price=1020.0,
    )

    result = pipeline.run(
        create_candidate_prices(),
        order_type=OrderType.LIMIT,
        limit_price=1000.0,
        report_generated_at=CURRENT_TIME,
    )

    assert result.approved_count == 1
    assert result.executed_count == 1
    assert result.failed_count == 0

    item = result.execution_batch_result.items[0]

    assert item.decision is (
        ExecutionDecision.ACTIVE
    )
    assert item.order_record is not None
    assert item.order_record.status is (
        OrderStatus.SENT
    )

    assert order_repository.count(
        status=OrderStatus.SENT,
    ) == 1
    assert broker.list_positions() == []

    assert result.execution_report.active_count == 1
    assert result.execution_report.filled_count == 0


def test_pipeline_writes_execution_report_csv(
    tmp_path: Path,
) -> None:
    """End-to-End実行結果をCSVへ保存する。"""

    (
        _signal_repository,
        _order_repository,
        _broker,
        pipeline,
    ) = create_environment(
        tmp_path
    )

    output_path = (
        tmp_path
        / "reports"
        / "paper_execution.csv"
    )

    result = pipeline.run(
        create_candidate_prices(),
        report_generated_at=CURRENT_TIME,
        report_csv_path=output_path,
    )

    assert result.report_csv_path == output_path
    assert output_path.exists()

    with output_path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as input_file:
        rows = list(
            csv.DictReader(
                input_file
            )
        )

    assert len(rows) == 1
    assert rows[0]["code"] == "7203"
    assert rows[0]["side"] == "buy"
    assert rows[0]["order_status"] == "filled"
    assert rows[0]["filled_quantity"] == "100"
    assert rows[0]["average_fill_price"] == (
        "1020.0"
    )