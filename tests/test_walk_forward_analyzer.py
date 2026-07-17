"""WalkForwardAnalyzerのテスト。"""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

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
from app.backtest.walk_forward_analyzer import (
    WalkForwardAnalyzer,
)
from app.backtest.walk_forward_runner import (
    WalkForwardRunner,
)
from app.backtest.walk_forward_window_service import (
    WalkForwardWindowService,
)
from app.trading.equity_curve_models import (
    EquityCurvePoint,
    EquityCurveReport,
)


JST = ZoneInfo("Asia/Tokyo")


def create_series(
    trading_day_count: int = 8,
) -> HistoricalBarSeries:
    """指定日数・各日1本の5分足系列を作成する。"""

    start = datetime(
        2026,
        7,
        1,
        9,
        0,
        tzinfo=JST,
    )

    return HistoricalBarSeries(
        code="7203",
        timeframe=MarketTimeframe.MINUTE_5,
        bars=tuple(
            HistoricalBar(
                code="7203",
                timeframe=MarketTimeframe.MINUTE_5,
                opened_at=start + timedelta(days=index),
                open_price=1000.0 + index,
                high_price=1010.0 + index,
                low_price=990.0 + index,
                close_price=1005.0 + index,
                volume=1000.0,
            )
            for index in range(trading_day_count)
        ),
    )


def create_metrics(
    *,
    trade_count: int,
    wins: int,
    losses: int,
    flats: int,
    gross_profit: float,
    gross_loss: float,
) -> BacktestPerformanceMetrics:
    """集計確認用の成績指標を作成する。"""

    net_profit = gross_profit - gross_loss

    return BacktestPerformanceMetrics(
        trade_count=trade_count,
        winning_trade_count=wins,
        losing_trade_count=losses,
        flat_trade_count=flats,
        gross_profit=gross_profit,
        gross_loss=gross_loss,
        net_profit_loss=net_profit,
        win_rate=(
            None
            if trade_count == 0
            else wins / trade_count
        ),
        profit_factor=(
            None
            if gross_loss == 0
            else gross_profit / gross_loss
        ),
        average_profit=None,
        average_loss=None,
        expectancy=(
            None
            if trade_count == 0
            else net_profit / trade_count
        ),
        maximum_consecutive_wins=wins,
        maximum_consecutive_losses=losses,
        unmatched_buy_quantity=0,
        unmatched_sell_quantity=0,
    )


def create_equity(
    drawdown: float,
) -> EquityCurveReport:
    """指定ドローダウンの資産曲線を作成する。"""

    point = EquityCurvePoint(
        generated_at=datetime(
            2026,
            7,
            1,
            tzinfo=timezone.utc,
        ),
        equity=1_000_000.0,
        cash_balance=1_000_000.0,
        market_value=0.0,
        realized_profit_loss=0.0,
        unrealized_profit_loss=0.0,
        period_return=None,
        cumulative_return=0.0,
    )

    return EquityCurveReport(
        points=(point,),
        initial_equity=1_000_000.0,
        final_equity=1_000_000.0,
        absolute_profit_loss=0.0,
        total_return=0.0,
        maximum_drawdown=drawdown,
        maximum_drawdown_amount=drawdown * 1_000_000.0,
        winning_period_count=0,
        losing_period_count=0,
        flat_period_count=0,
    )


def parameters() -> tuple[
    OrbOptimizationParameters,
    OrbOptimizationParameters,
]:
    """テスト用パラメータ候補を返す。"""

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


def create_result():
    """2ウィンドウの正常完了結果を作成する。"""

    first, second = parameters()
    plan = WalkForwardWindowService().create_plan(
        create_series(),
        training_days=4,
        validation_days=2,
        step_days=2,
    )
    validation_index = 0

    def training_executor(
        _series: HistoricalBarSeries,
        parameter: OrbOptimizationParameters,
    ) -> OrbOptimizationExecutionOutput:
        if parameter == first:
            metrics = create_metrics(
                trade_count=2,
                wins=1,
                losses=1,
                flats=0,
                gross_profit=200.0,
                gross_loss=100.0,
            )
        else:
            metrics = create_metrics(
                trade_count=3,
                wins=2,
                losses=1,
                flats=0,
                gross_profit=500.0,
                gross_loss=100.0,
            )

        return OrbOptimizationExecutionOutput(
            metrics=metrics,
            equity_curve_report=create_equity(0.10),
        )

    def validation_executor(
        _series: HistoricalBarSeries,
        parameter: OrbOptimizationParameters,
    ) -> OrbOptimizationExecutionOutput:
        nonlocal validation_index
        validation_index += 1

        if validation_index == 1:
            metrics = create_metrics(
                trade_count=2,
                wins=1,
                losses=1,
                flats=0,
                gross_profit=300.0,
                gross_loss=100.0,
            )
            drawdown = 0.08
        else:
            metrics = create_metrics(
                trade_count=3,
                wins=1,
                losses=2,
                flats=0,
                gross_profit=50.0,
                gross_loss=150.0,
            )
            drawdown = 0.15

        return OrbOptimizationExecutionOutput(
            metrics=metrics,
            equity_curve_report=create_equity(drawdown),
        )

    return WalkForwardRunner(
        training_executor=training_executor,
        validation_executor=validation_executor,
    ).run(
        plan,
        grid=OrbOptimizationGrid(
            parameters=(first, second)
        ),
    )


def test_analyzer_aggregates_validation_metrics() -> None:
    """OOS検証成績を取引件数ベースで合算する。"""

    summary = WalkForwardAnalyzer().create_summary(
        create_result()
    )
    validation = summary.validation

    assert validation.result_count == 2
    assert validation.trade_count == 5
    assert validation.winning_trade_count == 2
    assert validation.losing_trade_count == 3
    assert validation.gross_profit == 350.0
    assert validation.gross_loss == 250.0
    assert validation.net_profit_loss == 100.0
    assert validation.win_rate == pytest.approx(0.4)
    assert validation.profit_factor == pytest.approx(1.4)
    assert validation.expectancy == pytest.approx(20.0)
    assert validation.average_net_profit_loss == pytest.approx(
        50.0
    )
    assert validation.maximum_drawdown == pytest.approx(0.15)


def test_analyzer_aggregates_best_training_metrics() -> None:
    """各ウィンドウで選択された学習成績を合算する。"""

    summary = WalkForwardAnalyzer().create_summary(
        create_result()
    )
    training = summary.training

    assert training.result_count == 2
    assert training.trade_count == 6
    assert training.winning_trade_count == 4
    assert training.losing_trade_count == 2
    assert training.gross_profit == 1000.0
    assert training.gross_loss == 200.0
    assert training.net_profit_loss == 800.0
    assert training.win_rate == pytest.approx(4 / 6)
    assert training.profit_factor == pytest.approx(5.0)
    assert training.expectancy == pytest.approx(800 / 6)
    assert training.average_net_profit_loss == 400.0
    assert training.maximum_drawdown == pytest.approx(0.10)


def test_analyzer_counts_profitable_validation_windows() -> None:
    """利益が正のOOSウィンドウ件数と率を算出する。"""

    summary = WalkForwardAnalyzer().create_summary(
        create_result()
    )

    assert summary.window_count == 2
    assert summary.completed_window_count == 2
    assert summary.failed_window_count == 0
    assert summary.profitable_validation_window_count == 1
    assert (
        summary.validation_profitable_window_rate
        == pytest.approx(0.5)
    )


def test_analyzer_counts_selected_parameters() -> None:
    """採用パラメータの出現回数を集計する。"""

    result = create_result()
    summary = WalkForwardAnalyzer().create_summary(result)

    assert len(summary.parameter_frequencies) == 1
    frequency = summary.parameter_frequencies[0]
    assert frequency.parameter_id == (
        result.window_results[0]
        .selected_parameter.parameter_id
    )
    assert frequency.selected_count == 2


def test_analyzer_excludes_failed_windows() -> None:
    """失敗ウィンドウを成績集計から除外する。"""

    first, second = parameters()
    plan = WalkForwardWindowService().create_plan(
        create_series(),
        training_days=4,
        validation_days=2,
        step_days=2,
    )
    validation_count = 0

    def validation_executor(
        _series: HistoricalBarSeries,
        _parameter: OrbOptimizationParameters,
    ) -> OrbOptimizationExecutionOutput:
        nonlocal validation_count
        validation_count += 1

        if validation_count == 1:
            raise RuntimeError("validation failed")

        return OrbOptimizationExecutionOutput(
            metrics=create_metrics(
                trade_count=1,
                wins=1,
                losses=0,
                flats=0,
                gross_profit=100.0,
                gross_loss=0.0,
            ),
            equity_curve_report=None,
        )

    result = WalkForwardRunner(
        training_executor=lambda _series, _parameter: (
            OrbOptimizationExecutionOutput(
                metrics=create_metrics(
                    trade_count=1,
                    wins=1,
                    losses=0,
                    flats=0,
                    gross_profit=50.0,
                    gross_loss=0.0,
                ),
                equity_curve_report=None,
            )
        ),
        validation_executor=validation_executor,
    ).run(
        plan,
        grid=OrbOptimizationGrid(
            parameters=(first, second)
        ),
        continue_on_error=True,
    )

    summary = WalkForwardAnalyzer().create_summary(result)

    assert summary.window_count == 2
    assert summary.completed_window_count == 1
    assert summary.failed_window_count == 1
    assert summary.validation.result_count == 1
    assert summary.validation.net_profit_loss == 100.0


def test_analyzer_handles_empty_result() -> None:
    """空プランの結果を空集計へ変換する。"""

    first, second = parameters()
    plan = WalkForwardWindowService().create_plan(
        create_series(3),
        training_days=3,
        validation_days=1,
    )
    result = WalkForwardRunner(
        training_executor=lambda _series, _parameter: (
            OrbOptimizationExecutionOutput(
                metrics=create_metrics(
                    trade_count=0,
                    wins=0,
                    losses=0,
                    flats=0,
                    gross_profit=0.0,
                    gross_loss=0.0,
                ),
                equity_curve_report=None,
            )
        ),
        validation_executor=lambda _series, _parameter: (
            OrbOptimizationExecutionOutput(
                metrics=create_metrics(
                    trade_count=0,
                    wins=0,
                    losses=0,
                    flats=0,
                    gross_profit=0.0,
                    gross_loss=0.0,
                ),
                equity_curve_report=None,
            )
        ),
    ).run(
        plan,
        grid=OrbOptimizationGrid(
            parameters=(first, second)
        ),
    )

    summary = WalkForwardAnalyzer().create_summary(result)

    assert summary.window_count == 0
    assert summary.completed_window_count == 0
    assert summary.failed_window_count == 0
    assert summary.validation_profitable_window_rate is None
    assert summary.training.result_count == 0
    assert summary.validation.result_count == 0
    assert summary.validation.win_rate is None
    assert summary.validation.profit_factor is None
    assert summary.validation.expectancy is None
    assert summary.validation.maximum_drawdown is None
    assert summary.parameter_frequencies == ()


def test_analyzer_returns_none_profit_factor_without_losses() -> None:
    """総損失0の場合はProfit FactorをNoneにする。"""

    first, second = parameters()
    plan = WalkForwardWindowService().create_plan(
        create_series(6),
        training_days=4,
        validation_days=2,
    )
    output = OrbOptimizationExecutionOutput(
        metrics=create_metrics(
            trade_count=1,
            wins=1,
            losses=0,
            flats=0,
            gross_profit=100.0,
            gross_loss=0.0,
        ),
        equity_curve_report=None,
    )
    result = WalkForwardRunner(
        training_executor=lambda _series, _parameter: output,
        validation_executor=lambda _series, _parameter: output,
    ).run(
        plan,
        grid=OrbOptimizationGrid(
            parameters=(first, second)
        ),
    )

    summary = WalkForwardAnalyzer().create_summary(result)

    assert summary.validation.profit_factor is None
    assert summary.validation.win_rate == 1.0


def test_parameter_frequencies_are_sorted() -> None:
    """採用回数降順・ID昇順で安定して並べる。"""

    first, second = parameters()
    plan = WalkForwardWindowService().create_plan(
        create_series(10),
        training_days=4,
        validation_days=2,
        step_days=2,
    )
    window_index = 0

    def training_executor(
        series: HistoricalBarSeries,
        parameter: OrbOptimizationParameters,
    ) -> OrbOptimizationExecutionOutput:
        nonlocal window_index
        first_date = series.bars[0].opened_at.date()
        offset = (first_date.day - 1) // 2
        prefer_first = offset == 0
        profit = (
            200.0
            if (
                (prefer_first and parameter == first)
                or (not prefer_first and parameter == second)
            )
            else 100.0
        )

        return OrbOptimizationExecutionOutput(
            metrics=create_metrics(
                trade_count=1,
                wins=1,
                losses=0,
                flats=0,
                gross_profit=profit,
                gross_loss=0.0,
            ),
            equity_curve_report=None,
        )

    output = OrbOptimizationExecutionOutput(
        metrics=create_metrics(
            trade_count=1,
            wins=1,
            losses=0,
            flats=0,
            gross_profit=10.0,
            gross_loss=0.0,
        ),
        equity_curve_report=None,
    )
    result = WalkForwardRunner(
        training_executor=training_executor,
        validation_executor=lambda _series, _parameter: output,
    ).run(
        plan,
        grid=OrbOptimizationGrid(
            parameters=(first, second)
        ),
    )

    summary = WalkForwardAnalyzer().create_summary(result)

    assert [
        item.selected_count
        for item in summary.parameter_frequencies
    ] == [2, 1]
    assert summary.parameter_frequencies[0].parameter_id == (
        second.parameter_id
    )
