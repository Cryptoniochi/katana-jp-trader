"""定刻Paper Tradingランナーのテスト。"""

from datetime import date, datetime, time, timezone

import pytest

from app.market.models import StockPrice
from app.trading.order_models import OrderType
from app.trading.scheduled_paper_runner import (
    InMemoryScheduledRunStateStore,
    ScheduledPaperRunnerSettings,
    ScheduledPaperRunDecision,
    ScheduledPaperTradingRunner,
)


MONDAY_BEFORE = datetime(
    2026,
    7,
    20,
    0,
    20,
    tzinfo=timezone.utc,
)

MONDAY_AFTER = datetime(
    2026,
    7,
    20,
    0,
    30,
    tzinfo=timezone.utc,
)

SATURDAY = datetime(
    2026,
    7,
    18,
    0,
    30,
    tzinfo=timezone.utc,
)


def create_price() -> StockPrice:
    """ランナー用の価格データを作成する。"""

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
        prices: list[StockPrice],
    ) -> None:
        """返す価格を設定する。"""

        self.prices = prices
        self.requested_dates: list[date] = []

    def load(
        self,
        *,
        trading_date: date,
    ) -> list[StockPrice]:
        """価格データを返す。"""

        self.requested_dates.append(
            trading_date,
        )

        return list(
            self.prices,
        )


class FakePipelineResult:
    """パイプライン結果の最小実装。"""

    def __init__(
        self,
        *,
        successful: bool = True,
    ) -> None:
        """成功状態を設定する。"""

        self._successful = successful

    @property
    def is_successful(self) -> bool:
        """成功状態を返す。"""

        return self._successful


class FakePipeline:
    """呼び出し内容を記録するPipeline。"""

    def __init__(
        self,
        *,
        successful: bool = True,
    ) -> None:
        """結果状態を設定する。"""

        self.successful = successful
        self.calls: list[
            tuple[
                list[StockPrice],
                OrderType,
                float | None,
                float | None,
            ]
        ] = []

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
        """呼び出し内容を保存して固定結果を返す。"""

        del report_generated_at
        del report_csv_path
        del continue_on_error

        self.calls.append(
            (
                list(prices),
                order_type,
                limit_price,
                stop_price,
            )
        )

        return FakePipelineResult(
            successful=self.successful,
        )


def create_runner(
    *,
    prices: list[StockPrice] | None = None,
    pipeline_successful: bool = True,
    state_store: (
        InMemoryScheduledRunStateStore | None
    ) = None,
    settings: ScheduledPaperRunnerSettings | None = None,
) -> tuple[
    FakePriceLoader,
    FakePipeline,
    InMemoryScheduledRunStateStore,
    ScheduledPaperTradingRunner,
]:
    """標準ランナーを作成する。"""

    loader = FakePriceLoader(
        prices=(
            prices
            if prices is not None
            else [create_price()]
        )
    )
    pipeline = FakePipeline(
        successful=pipeline_successful,
    )
    resolved_store = (
        state_store
        if state_store is not None
        else InMemoryScheduledRunStateStore()
    )

    runner = ScheduledPaperTradingRunner(
        price_loader=loader,
        pipeline=pipeline,
        state_store=resolved_store,
        settings=settings,
    )

    return (
        loader,
        pipeline,
        resolved_store,
        runner,
    )


def test_runner_executes_after_scheduled_time() -> None:
    """平日の指定時刻後に一度だけ実行する。"""

    loader, pipeline, store, runner = create_runner()

    result = runner.run_once(
        now=MONDAY_AFTER,
    )

    assert result.decision is (
        ScheduledPaperRunDecision.EXECUTED
    )
    assert result.was_executed is True
    assert result.was_skipped is False
    assert result.is_failed is False
    assert result.trading_date == date(
        2026,
        7,
        20,
    )
    assert result.price_count == 1
    assert result.pipeline_result is not None
    assert result.message is None

    assert loader.requested_dates == [
        date(
            2026,
            7,
            20,
        )
    ]
    assert len(
        pipeline.calls
    ) == 1
    assert store.has_completed(
        trading_date=date(
            2026,
            7,
            20,
        ),
        process_name="paper-trading",
    )


def test_runner_skips_before_execution_time() -> None:
    """指定時刻より前は実行しない。"""

    loader, pipeline, _store, runner = create_runner()

    result = runner.run_once(
        now=MONDAY_BEFORE,
    )

    assert result.decision is (
        ScheduledPaperRunDecision.SKIPPED_BEFORE_TIME
    )
    assert result.was_skipped is True
    assert loader.requested_dates == []
    assert pipeline.calls == []


def test_runner_skips_weekend() -> None:
    """土曜日は実行しない。"""

    loader, pipeline, _store, runner = create_runner()

    result = runner.run_once(
        now=SATURDAY,
    )

    assert result.decision is (
        ScheduledPaperRunDecision
        .SKIPPED_NON_TRADING_DAY
    )
    assert result.was_skipped is True
    assert loader.requested_dates == []
    assert pipeline.calls == []


def test_runner_skips_second_run_on_same_day() -> None:
    """同日の二回目以降をスキップする。"""

    loader, pipeline, _store, runner = create_runner()

    first = runner.run_once(
        now=MONDAY_AFTER,
    )
    second = runner.run_once(
        now=MONDAY_AFTER,
    )

    assert first.was_executed is True
    assert second.decision is (
        ScheduledPaperRunDecision
        .SKIPPED_ALREADY_COMPLETED
    )
    assert len(
        loader.requested_dates
    ) == 1
    assert len(
        pipeline.calls
    ) == 1


def test_runner_skips_without_prices() -> None:
    """価格データがない場合は完了扱いにしない。"""

    loader, pipeline, store, runner = create_runner(
        prices=[],
    )

    result = runner.run_once(
        now=MONDAY_AFTER,
    )

    assert result.decision is (
        ScheduledPaperRunDecision.SKIPPED_NO_PRICES
    )
    assert result.price_count == 0
    assert pipeline.calls == []
    assert not store.has_completed(
        trading_date=date(
            2026,
            7,
            20,
        ),
        process_name="paper-trading",
    )
    assert loader.requested_dates == [
        date(
            2026,
            7,
            20,
        )
    ]


def test_runner_records_failed_pipeline_result() -> None:
    """失敗結果をFAILEDへ変換し完了扱いにしない。"""

    _loader, pipeline, store, runner = create_runner(
        pipeline_successful=False,
    )

    result = runner.run_once(
        now=MONDAY_AFTER,
        continue_on_error=True,
    )

    assert result.decision is (
        ScheduledPaperRunDecision.FAILED
    )
    assert result.is_failed is True
    assert "失敗結果" in (
        result.message or ""
    )
    assert len(
        pipeline.calls
    ) == 1
    assert not store.has_completed(
        trading_date=date(
            2026,
            7,
            20,
        ),
        process_name="paper-trading",
    )


def test_runner_raises_pipeline_failure_when_disabled() -> None:
    """continue_on_error無効時は失敗を再送出する。"""

    _loader, _pipeline, _store, runner = create_runner(
        pipeline_successful=False,
    )

    with pytest.raises(
        RuntimeError,
        match="失敗結果",
    ):
        runner.run_once(
            now=MONDAY_AFTER,
            continue_on_error=False,
        )


def test_runner_passes_order_settings_to_pipeline() -> None:
    """注文種別・価格設定をPipelineへ渡す。"""

    settings = ScheduledPaperRunnerSettings(
        execution_time=time(
            9,
            25,
        ),
        order_type=OrderType.LIMIT,
        limit_price=1000.0,
    )

    _loader, pipeline, _store, runner = create_runner(
        settings=settings,
    )

    runner.run_once(
        now=MONDAY_AFTER,
    )

    assert len(
        pipeline.calls
    ) == 1

    (
        _prices,
        order_type,
        limit_price,
        stop_price,
    ) = pipeline.calls[0]

    assert order_type is OrderType.LIMIT
    assert limit_price == pytest.approx(
        1000.0,
    )
    assert stop_price is None


def test_runner_rejects_naive_now() -> None:
    """タイムゾーンなし現在日時を拒否する。"""

    _loader, _pipeline, _store, runner = create_runner()

    with pytest.raises(
        ValueError,
        match="タイムゾーン",
    ):
        runner.run_once(
            now=datetime(
                2026,
                7,
                20,
                9,
                30,
            ),
        )


@pytest.mark.parametrize(
    (
        "arguments",
        "message",
    ),
    [
        (
            {
                "process_name": " ",
            },
            "処理名",
        ),
        (
            {
                "order_type": OrderType.LIMIT,
                "limit_price": None,
            },
            "指値価格",
        ),
        (
            {
                "order_type": OrderType.STOP,
                "stop_price": None,
            },
            "逆指値価格",
        ),
        (
            {
                "order_type": OrderType.MARKET,
                "limit_price": 1000.0,
            },
            "成行注文",
        ),
    ],
)
def test_runner_settings_reject_invalid_values(
    arguments: dict[str, object],
    message: str,
) -> None:
    """不正な定刻実行設定を拒否する。"""

    with pytest.raises(
        ValueError,
        match=message,
    ):
        ScheduledPaperRunnerSettings(
            **arguments,
        )