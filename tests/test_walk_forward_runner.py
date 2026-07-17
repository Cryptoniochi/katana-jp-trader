"""WalkForwardRunnerのテスト。"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.backtest.composite_score_models import (
    CompositeScoreWeights,
)
from app.backtest.historical_models import (
    HistoricalBar,
    HistoricalBarSeries,
    MarketTimeframe,
)
from app.backtest.optimization_models import (
    OrbOptimizationGrid,
    OrbOptimizationParameters,
)
from app.backtest.optimization_runner import (
    OrbOptimizationExecutionOutput,
)
from app.backtest.performance_metrics_models import (
    BacktestPerformanceMetrics,
)
from app.backtest.walk_forward_result_models import (
    WalkForwardWindowStatus,
)
from app.backtest.walk_forward_runner import (
    WalkForwardRunner,
)
from app.backtest.walk_forward_window_service import (
    WalkForwardWindowService,
)


JST = ZoneInfo("Asia/Tokyo")


def create_series(
    trading_day_count: int = 8,
) -> HistoricalBarSeries:
    """指定日数・各日1本の系列を作成する。"""

    bars = tuple(
        HistoricalBar(
            code="7203",
            timeframe=MarketTimeframe.MINUTE_5,
            opened_at=datetime(
                2026,
                7,
                1,
                9,
                0,
                tzinfo=JST,
            )
            + timedelta(days=index),
            open_price=1000.0 + index,
            high_price=1010.0 + index,
            low_price=990.0 + index,
            close_price=1005.0 + index,
            volume=1000.0,
        )
        for index in range(trading_day_count)
    )

    return HistoricalBarSeries(
        code="7203",
        timeframe=MarketTimeframe.MINUTE_5,
        bars=bars,
    )


def metrics(
    profit: float,
    *,
    profit_factor: float | None = None,
    win_rate: float | None = None,
) -> BacktestPerformanceMetrics:
    """テスト用成績指標を作成する。"""

    winner = profit > 0
    loser = profit < 0

    return BacktestPerformanceMetrics(
        trade_count=1,
        winning_trade_count=int(winner),
        losing_trade_count=int(loser),
        flat_trade_count=int(profit == 0),
        gross_profit=max(0.0, profit),
        gross_loss=max(0.0, -profit),
        net_profit_loss=profit,
        win_rate=(
            win_rate
            if win_rate is not None
            else (1.0 if winner else 0.0)
        ),
        profit_factor=profit_factor,
        average_profit=profit if winner else None,
        average_loss=-profit if loser else None,
        expectancy=profit,
        maximum_consecutive_wins=int(winner),
        maximum_consecutive_losses=int(loser),
        unmatched_buy_quantity=0,
        unmatched_sell_quantity=0,
    )


def parameters() -> tuple[
    OrbOptimizationParameters,
    OrbOptimizationParameters,
]:
    """テスト用候補を返す。"""

    return (
        OrbOptimizationParameters(
            stop_loss_rate=0.01,
            take_profit_rate=0.02,
            opening_range_end=time(9, 10),
        ),
        OrbOptimizationParameters(
            stop_loss_rate=0.02,
            take_profit_rate=0.04,
            opening_range_end=time(9, 15),
        ),
    )


def create_plan():
    """2ウィンドウのプランを作成する。"""

    return WalkForwardWindowService().create_plan(
        create_series(),
        training_days=4,
        validation_days=2,
        step_days=2,
    )


def test_runner_optimizes_and_validates_each_window() -> None:
    """各ウィンドウで学習後に最良候補を検証する。"""

    first, second = parameters()
    training_calls: list[tuple[int, str]] = []
    validation_calls: list[tuple[int, str]] = []

    def training_executor(
        series: HistoricalBarSeries,
        parameter: OrbOptimizationParameters,
    ) -> OrbOptimizationExecutionOutput:
        training_calls.append(
            (series.bar_count, parameter.parameter_id)
        )
        profit = 100.0 if parameter == first else 300.0

        return OrbOptimizationExecutionOutput(
            metrics=metrics(profit),
            equity_curve_report=None,
        )

    def validation_executor(
        series: HistoricalBarSeries,
        parameter: OrbOptimizationParameters,
    ) -> OrbOptimizationExecutionOutput:
        validation_calls.append(
            (series.bar_count, parameter.parameter_id)
        )

        return OrbOptimizationExecutionOutput(
            metrics=metrics(50.0),
            equity_curve_report=None,
        )

    result = WalkForwardRunner(
        training_executor=training_executor,
        validation_executor=validation_executor,
    ).run(
        create_plan(),
        grid=OrbOptimizationGrid(
            parameters=(first, second)
        ),
    )

    assert result.window_count == 2
    assert result.completed_count == 2
    assert result.failed_count == 0
    assert len(training_calls) == 4
    assert validation_calls == [
        (2, second.parameter_id),
        (2, second.parameter_id),
    ]

    for window_result in result.window_results:
        assert window_result.is_completed
        assert (
            window_result.selected_parameter
            == second
        )
        assert (
            window_result.validation_result
            is not None
        )
        assert (
            window_result.validation_result
            .metrics.net_profit_loss
            == 50.0
        )


def test_runner_supports_win_rate_ranking() -> None:
    """単一指標ランキングを切り替えられる。"""

    first, second = parameters()
    validated: list[str] = []

    def training_executor(
        _series: HistoricalBarSeries,
        parameter: OrbOptimizationParameters,
    ) -> OrbOptimizationExecutionOutput:
        if parameter == first:
            result_metrics = metrics(
                500.0,
                win_rate=0.4,
            )
        else:
            result_metrics = metrics(
                100.0,
                win_rate=0.8,
            )

        return OrbOptimizationExecutionOutput(
            metrics=result_metrics,
            equity_curve_report=None,
        )

    def validation_executor(
        _series: HistoricalBarSeries,
        parameter: OrbOptimizationParameters,
    ) -> OrbOptimizationExecutionOutput:
        validated.append(parameter.parameter_id)

        return OrbOptimizationExecutionOutput(
            metrics=metrics(10.0),
            equity_curve_report=None,
        )

    result = WalkForwardRunner(
        training_executor=training_executor,
        validation_executor=validation_executor,
    ).run(
        create_plan(),
        grid=OrbOptimizationGrid(
            parameters=(first, second)
        ),
        ranking_method="win_rate",
    )

    assert result.completed_count == 2
    assert validated == [
        second.parameter_id,
        second.parameter_id,
    ]
    assert all(
        item.best_training_score == 0.8
        for item in result.window_results
    )


def test_runner_supports_composite_ranking() -> None:
    """複合スコアで最良候補を選択する。"""

    first, second = parameters()
    validated: list[str] = []

    def training_executor(
        _series: HistoricalBarSeries,
        parameter: OrbOptimizationParameters,
    ) -> OrbOptimizationExecutionOutput:
        if parameter == first:
            result_metrics = metrics(
                1000.0,
                profit_factor=1.0,
                win_rate=0.4,
            )
        else:
            result_metrics = metrics(
                500.0,
                profit_factor=3.0,
                win_rate=0.8,
            )

        return OrbOptimizationExecutionOutput(
            metrics=result_metrics,
            equity_curve_report=None,
        )

    def validation_executor(
        _series: HistoricalBarSeries,
        parameter: OrbOptimizationParameters,
    ) -> OrbOptimizationExecutionOutput:
        validated.append(parameter.parameter_id)

        return OrbOptimizationExecutionOutput(
            metrics=metrics(20.0),
            equity_curve_report=None,
        )

    result = WalkForwardRunner(
        training_executor=training_executor,
        validation_executor=validation_executor,
    ).run(
        create_plan(),
        grid=OrbOptimizationGrid(
            parameters=(first, second)
        ),
        ranking_method="composite",
        composite_weights=CompositeScoreWeights(
            net_profit=0.0,
            profit_factor=0.5,
            win_rate=0.5,
            maximum_drawdown=0.0,
        ),
    )

    assert result.completed_count == 2
    assert validated == [
        second.parameter_id,
        second.parameter_id,
    ]
    assert all(
        item.composite_score_report is not None
        for item in result.window_results
    )
    assert all(
        item.best_training_score == pytest.approx(1.0)
        for item in result.window_results
    )


def test_runner_continues_after_validation_error() -> None:
    """continue_on_error時は失敗ウィンドウを保存して続行する。"""

    first, second = parameters()
    validation_count = 0

    def training_executor(
        _series: HistoricalBarSeries,
        parameter: OrbOptimizationParameters,
    ) -> OrbOptimizationExecutionOutput:
        return OrbOptimizationExecutionOutput(
            metrics=metrics(
                100.0 if parameter == first else 200.0
            ),
            equity_curve_report=None,
        )

    def validation_executor(
        _series: HistoricalBarSeries,
        _parameter: OrbOptimizationParameters,
    ) -> OrbOptimizationExecutionOutput:
        nonlocal validation_count
        validation_count += 1

        if validation_count == 1:
            raise RuntimeError("validation failed")

        return OrbOptimizationExecutionOutput(
            metrics=metrics(50.0),
            equity_curve_report=None,
        )

    result = WalkForwardRunner(
        training_executor=training_executor,
        validation_executor=validation_executor,
    ).run(
        create_plan(),
        grid=OrbOptimizationGrid(
            parameters=(first, second)
        ),
        continue_on_error=True,
    )

    assert result.window_count == 2
    assert result.completed_count == 1
    assert result.failed_count == 1
    assert (
        result.window_results[0].status
        is WalkForwardWindowStatus.FAILED
    )
    assert (
        result.window_results[0].error_message
        == "validation failed"
    )
    assert result.window_results[1].is_completed


def test_runner_raises_window_error_by_default() -> None:
    """既定ではウィンドウ失敗を送出する。"""

    first, second = parameters()

    with pytest.raises(
        RuntimeError,
        match="validation failed",
    ):
        WalkForwardRunner(
            training_executor=lambda _series, _parameter: (
                OrbOptimizationExecutionOutput(
                    metrics=metrics(100.0),
                    equity_curve_report=None,
                )
            ),
            validation_executor=lambda _series, _parameter: (
                (_ for _ in ()).throw(
                    RuntimeError("validation failed")
                )
            ),
        ).run(
            create_plan(),
            grid=OrbOptimizationGrid(
                parameters=(first, second)
            ),
        )


def test_runner_fails_window_when_all_training_runs_fail() -> None:
    """全学習試行失敗時は検証せず失敗結果を作成する。"""

    first, second = parameters()
    validation_called = False

    def validation_executor(
        _series: HistoricalBarSeries,
        _parameter: OrbOptimizationParameters,
    ) -> OrbOptimizationExecutionOutput:
        nonlocal validation_called
        validation_called = True

        return OrbOptimizationExecutionOutput(
            metrics=metrics(0.0),
            equity_curve_report=None,
        )

    result = WalkForwardRunner(
        training_executor=lambda _series, _parameter: (
            (_ for _ in ()).throw(
                RuntimeError("training failed")
            )
        ),
        validation_executor=validation_executor,
    ).run(
        create_plan(),
        grid=OrbOptimizationGrid(
            parameters=(first, second)
        ),
        continue_on_error=True,
    )

    assert result.completed_count == 0
    assert result.failed_count == 2
    assert validation_called is False
    assert all(
        "正常完了した学習試行がない"
        in (item.error_message or "")
        for item in result.window_results
    )


def test_runner_accepts_empty_plan() -> None:
    """空プランでは空結果を返す。"""

    empty_plan = (
        WalkForwardWindowService()
        .create_plan(
            create_series(3),
            training_days=3,
            validation_days=1,
        )
    )

    result = WalkForwardRunner(
        training_executor=lambda _series, _parameter: (
            OrbOptimizationExecutionOutput(
                metrics=metrics(0.0),
                equity_curve_report=None,
            )
        ),
        validation_executor=lambda _series, _parameter: (
            OrbOptimizationExecutionOutput(
                metrics=metrics(0.0),
                equity_curve_report=None,
            )
        ),
    ).run(
        empty_plan,
        grid=OrbOptimizationGrid(
            parameters=parameters()
        ),
    )

    assert result.window_results == ()
    assert result.window_count == 0


def test_runner_rejects_unknown_ranking_method() -> None:
    """未対応ランキング方式を拒否する。"""

    with pytest.raises(ValueError, match="未対応"):
        WalkForwardRunner(
            training_executor=lambda _series, _parameter: (
                OrbOptimizationExecutionOutput(
                    metrics=metrics(0.0),
                    equity_curve_report=None,
                )
            ),
            validation_executor=lambda _series, _parameter: (
                OrbOptimizationExecutionOutput(
                    metrics=metrics(0.0),
                    equity_curve_report=None,
                )
            ),
        ).run(
            create_plan(),
            grid=OrbOptimizationGrid(
                parameters=parameters()
            ),
            ranking_method="unknown",
        )
