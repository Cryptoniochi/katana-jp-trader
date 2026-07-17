"""OrbOptimizationRunnerのテスト。"""

from datetime import time

import pytest

from app.backtest.optimization_models import (
    OrbOptimizationGrid,
    OrbOptimizationParameters,
)
from app.backtest.optimization_result_models import (
    OptimizationRunStatus,
    OrbOptimizationResult,
)
from app.backtest.optimization_runner import (
    OrbOptimizationExecutionOutput,
    OrbOptimizationRunner,
)
from app.backtest.performance_metrics_models import (
    BacktestPerformanceMetrics,
)


def parameter(
    stop_loss_rate: float,
    take_profit_rate: float,
    opening_range_end: time,
) -> OrbOptimizationParameters:
    """テスト用最適化パラメータを作成する。"""

    return OrbOptimizationParameters(
        stop_loss_rate=stop_loss_rate,
        take_profit_rate=take_profit_rate,
        opening_range_end=opening_range_end,
    )


def metrics(
    *,
    net_profit_loss: float,
) -> BacktestPerformanceMetrics:
    """テスト用成績指標を作成する。"""

    winner = net_profit_loss > 0
    loser = net_profit_loss < 0
    flat = net_profit_loss == 0

    return BacktestPerformanceMetrics(
        trade_count=1,
        winning_trade_count=int(winner),
        losing_trade_count=int(loser),
        flat_trade_count=int(flat),
        gross_profit=max(0.0, net_profit_loss),
        gross_loss=max(0.0, -net_profit_loss),
        net_profit_loss=net_profit_loss,
        win_rate=1.0 if winner else 0.0,
        profit_factor=(
            None
            if not loser
            else 0.0
        ),
        average_profit=(
            net_profit_loss
            if winner
            else None
        ),
        average_loss=(
            -net_profit_loss
            if loser
            else None
        ),
        expectancy=net_profit_loss,
        maximum_consecutive_wins=int(winner),
        maximum_consecutive_losses=int(loser),
        unmatched_buy_quantity=0,
        unmatched_sell_quantity=0,
    )


def test_runner_executes_all_parameters_in_order() -> None:
    """グリッド順に全試行を実行する。"""

    parameters = (
        parameter(0.01, 0.03, time(9, 10)),
        parameter(0.02, 0.04, time(9, 15)),
        parameter(0.03, 0.05, time(9, 20)),
    )
    called: list[str] = []

    def executor(
        value: OrbOptimizationParameters,
    ) -> OrbOptimizationExecutionOutput:
        called.append(value.parameter_id)

        return OrbOptimizationExecutionOutput(
            metrics=metrics(
                net_profit_loss=(
                    value.stop_loss_rate or 0.0
                ) * 100_000.0
            ),
            equity_curve_report=None,
        )

    result = OrbOptimizationRunner(
        executor=executor
    ).run(
        OrbOptimizationGrid(
            parameters=parameters
        )
    )

    assert called == [
        item.parameter_id
        for item in parameters
    ]
    assert result.run_count == 3
    assert result.completed_count == 3
    assert result.failed_count == 0
    assert [
        run.parameter
        for run in result.runs
    ] == list(parameters)


def test_runner_links_metrics_to_parameter() -> None:
    """各パラメータに対応する成績を保持する。"""

    first = parameter(
        0.01,
        0.03,
        time(9, 10),
    )
    second = parameter(
        0.02,
        0.04,
        time(9, 15),
    )

    def executor(
        value: OrbOptimizationParameters,
    ) -> OrbOptimizationExecutionOutput:
        profit = (
            1000.0
            if value == first
            else 2000.0
        )

        return OrbOptimizationExecutionOutput(
            metrics=metrics(
                net_profit_loss=profit
            ),
            equity_curve_report=None,
        )

    result = OrbOptimizationRunner(
        executor=executor
    ).run(
        OrbOptimizationGrid(
            parameters=(first, second)
        )
    )

    assert result.get(
        first.parameter_id
    ).net_profit_loss == pytest.approx(1000.0)
    assert result.get(
        second.parameter_id
    ).net_profit_loss == pytest.approx(2000.0)


def test_runner_raises_error_by_default() -> None:
    """既定では試行失敗をそのまま送出する。"""

    grid = OrbOptimizationGrid(
        parameters=(
            parameter(
                0.02,
                0.04,
                time(9, 15),
            ),
        )
    )

    def executor(
        _value: OrbOptimizationParameters,
    ) -> OrbOptimizationExecutionOutput:
        raise RuntimeError("backtest failed")

    with pytest.raises(
        RuntimeError,
        match="backtest failed",
    ):
        OrbOptimizationRunner(
            executor=executor
        ).run(grid)


def test_runner_can_continue_after_error() -> None:
    """continue_on_error時は失敗を結果へ保存する。"""

    first = parameter(
        0.01,
        0.03,
        time(9, 10),
    )
    second = parameter(
        0.02,
        0.04,
        time(9, 15),
    )
    third = parameter(
        0.03,
        0.05,
        time(9, 20),
    )

    def executor(
        value: OrbOptimizationParameters,
    ) -> OrbOptimizationExecutionOutput:
        if value == second:
            raise RuntimeError("second failed")

        return OrbOptimizationExecutionOutput(
            metrics=metrics(
                net_profit_loss=1000.0
            ),
            equity_curve_report=None,
        )

    result = OrbOptimizationRunner(
        executor=executor
    ).run(
        OrbOptimizationGrid(
            parameters=(
                first,
                second,
                third,
            )
        ),
        continue_on_error=True,
    )

    assert result.run_count == 3
    assert result.completed_count == 2
    assert result.failed_count == 1
    assert result.runs[1].status is (
        OptimizationRunStatus.FAILED
    )
    assert result.runs[1].error_message == (
        "second failed"
    )


def test_runner_accepts_empty_grid() -> None:
    """空グリッドでは空結果を返す。"""

    result = OrbOptimizationRunner(
        executor=lambda _parameter: (
            OrbOptimizationExecutionOutput(
                metrics=metrics(
                    net_profit_loss=0.0
                ),
                equity_curve_report=None,
            )
        )
    ).run(
        OrbOptimizationGrid(parameters=())
    )

    assert result.runs == ()
    assert result.run_count == 0
    assert result.completed_runs == ()
    assert result.failed_runs == ()


def test_result_get_rejects_unknown_id() -> None:
    """存在しない結果IDを拒否する。"""

    result = OrbOptimizationResult(runs=())

    with pytest.raises(KeyError, match="存在しません"):
        result.get("missing")


def test_result_model_rejects_duplicate_parameters() -> None:
    """同じパラメータIDの重複結果を拒否する。"""

    value = parameter(
        0.02,
        0.04,
        time(9, 15),
    )
    output = OrbOptimizationExecutionOutput(
        metrics=metrics(
            net_profit_loss=1000.0
        ),
        equity_curve_report=None,
    )

    runner = OrbOptimizationRunner(
        executor=lambda _parameter: output
    )
    single = runner.run(
        OrbOptimizationGrid(
            parameters=(value,)
        )
    ).runs[0]

    with pytest.raises(ValueError, match="重複"):
        OrbOptimizationResult(
            runs=(single, single)
        )
