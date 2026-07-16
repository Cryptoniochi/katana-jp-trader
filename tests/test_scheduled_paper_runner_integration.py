"""SQLite状態保存を使う定刻Paper Tradingランナー統合テスト。"""

from datetime import date, datetime, timezone
from pathlib import Path

from app.database import initialize_database
from app.market.models import StockPrice
from app.trading.order_models import OrderType
from app.trading.scheduled_paper_runner import (
    ScheduledPaperRunDecision,
    ScheduledPaperTradingRunner,
)
from app.trading.scheduled_run_state_repository import (
    ScheduledRunStateRepository,
)


RUN_TIME = datetime(
    2026,
    7,
    20,
    0,
    30,
    tzinfo=timezone.utc,
)

TRADING_DATE = date(
    2026,
    7,
    20,
)


def create_price() -> StockPrice:
    """統合テスト用価格データを作成する。"""

    return StockPrice(
        code="7203",
        datetime=datetime(
            2026,
            7,
            20,
            9,
            20,
        ),
        open=1000.0,
        high=1020.0,
        low=995.0,
        close=1015.0,
        volume=200_000,
    )


class FakePriceLoader:
    """固定価格データを返すLoader。"""

    def __init__(
        self,
    ) -> None:
        """呼出回数を初期化する。"""

        self.call_count = 0

    def load(
        self,
        *,
        trading_date: date,
    ) -> list[StockPrice]:
        """指定日の価格データを返す。"""

        assert trading_date == TRADING_DATE

        self.call_count += 1

        return [
            create_price(),
        ]


class FakePipelineResult:
    """成功するパイプライン結果。"""

    @property
    def is_successful(self) -> bool:
        """成功を返す。"""

        return True


class FakePipeline:
    """呼出回数を記録するPipeline。"""

    def __init__(
        self,
    ) -> None:
        """呼出回数を初期化する。"""

        self.call_count = 0

    def run(
        self,
        prices: list[StockPrice],
        *,
        order_type: OrderType = OrderType.MARKET,
        limit_price: float | None = None,
        stop_price: float | None = None,
        report_generated_at: datetime | None = None,
        report_csv_path: object | None = None,
        continue_on_error: bool = True,
    ) -> FakePipelineResult:
        """成功結果を返す。"""

        del order_type
        del limit_price
        del stop_price
        del report_generated_at
        del report_csv_path
        del continue_on_error

        assert len(
            prices,
        ) == 1

        self.call_count += 1

        return FakePipelineResult()


def test_sqlite_store_prevents_second_run_after_restart(
    tmp_path: Path,
) -> None:
    """Runnerを作り直しても当日の二重実行を防止する。"""

    database_path = (
        tmp_path / "katana.db"
    )

    initialize_database(
        database_path,
    )

    first_loader = FakePriceLoader()
    first_pipeline = FakePipeline()

    first_runner = ScheduledPaperTradingRunner(
        price_loader=first_loader,
        pipeline=first_pipeline,
        state_store=(
            ScheduledRunStateRepository(
                database_path,
            )
        ),
    )

    first_result = first_runner.run_once(
        now=RUN_TIME,
    )

    assert first_result.decision is (
        ScheduledPaperRunDecision.EXECUTED
    )
    assert first_loader.call_count == 1
    assert first_pipeline.call_count == 1

    second_loader = FakePriceLoader()
    second_pipeline = FakePipeline()

    second_runner = ScheduledPaperTradingRunner(
        price_loader=second_loader,
        pipeline=second_pipeline,
        state_store=(
            ScheduledRunStateRepository(
                database_path,
            )
        ),
    )

    second_result = second_runner.run_once(
        now=RUN_TIME,
    )

    assert second_result.decision is (
        ScheduledPaperRunDecision
        .SKIPPED_ALREADY_COMPLETED
    )
    assert second_loader.call_count == 0
    assert second_pipeline.call_count == 0


def test_sqlite_store_allows_next_trading_date(
    tmp_path: Path,
) -> None:
    """翌取引日は新たに処理できる。"""

    database_path = (
        tmp_path / "katana.db"
    )

    initialize_database(
        database_path,
    )

    repository = ScheduledRunStateRepository(
        database_path,
    )

    repository.mark_completed(
        trading_date=TRADING_DATE,
        process_name="paper-trading",
        completed_at=RUN_TIME,
    )

    assert repository.has_completed(
        trading_date=TRADING_DATE,
        process_name="paper-trading",
    )

    assert not repository.has_completed(
        trading_date=date(
            2026,
            7,
            21,
        ),
        process_name="paper-trading",
    )


def test_sqlite_store_keeps_process_names_independent(
    tmp_path: Path,
) -> None:
    """異なる処理名の完了状態は互いに干渉しない。"""

    database_path = (
        tmp_path / "katana.db"
    )

    initialize_database(
        database_path,
    )

    repository = ScheduledRunStateRepository(
        database_path,
    )

    repository.mark_completed(
        trading_date=TRADING_DATE,
        process_name="jquants-update",
        completed_at=RUN_TIME,
    )

    loader = FakePriceLoader()
    pipeline = FakePipeline()

    runner = ScheduledPaperTradingRunner(
        price_loader=loader,
        pipeline=pipeline,
        state_store=repository,
    )

    result = runner.run_once(
        now=RUN_TIME,
    )

    assert result.decision is (
        ScheduledPaperRunDecision.EXECUTED
    )
    assert loader.call_count == 1
    assert pipeline.call_count == 1

    assert repository.has_completed(
        trading_date=TRADING_DATE,
        process_name="jquants-update",
    )
    assert repository.has_completed(
        trading_date=TRADING_DATE,
        process_name="paper-trading",
    )