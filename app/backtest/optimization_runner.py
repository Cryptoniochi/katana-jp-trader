"""ORB最適化グリッドを順番に実行する。"""

from collections.abc import Callable
from dataclasses import dataclass

from app.backtest.optimization_models import (
    OrbOptimizationGrid,
    OrbOptimizationParameters,
)
from app.backtest.optimization_result_models import (
    OptimizationRunStatus,
    OrbOptimizationResult,
    OrbOptimizationRunResult,
)
from app.backtest.performance_metrics_models import (
    BacktestPerformanceMetrics,
)
from app.trading.equity_curve_models import (
    EquityCurveReport,
)


@dataclass(frozen=True, slots=True)
class OrbOptimizationExecutionOutput:
    """1回のバックテスト実行から返す成績情報。"""

    metrics: BacktestPerformanceMetrics
    equity_curve_report: EquityCurveReport | None


OptimizationExecutor = Callable[
    [OrbOptimizationParameters],
    OrbOptimizationExecutionOutput,
]


class OrbOptimizationRunner:
    """最適化グリッドを安定した順序で実行する。"""

    def __init__(
        self,
        *,
        executor: OptimizationExecutor,
    ) -> None:
        """バックテスト実行処理を設定する。"""

        self.executor = executor

    def run(
        self,
        grid: OrbOptimizationGrid,
        *,
        continue_on_error: bool = False,
    ) -> OrbOptimizationResult:
        """グリッド内の全パラメータを順番に実行する。"""

        results: list[OrbOptimizationRunResult] = []

        for parameter in grid.parameters:
            try:
                output = self.executor(parameter)

                results.append(
                    OrbOptimizationRunResult(
                        parameter=parameter,
                        status=(
                            OptimizationRunStatus.COMPLETED
                        ),
                        metrics=output.metrics,
                        equity_curve_report=(
                            output.equity_curve_report
                        ),
                        error_message=None,
                    )
                )

            except Exception as error:
                if not continue_on_error:
                    raise

                results.append(
                    OrbOptimizationRunResult(
                        parameter=parameter,
                        status=OptimizationRunStatus.FAILED,
                        metrics=None,
                        equity_curve_report=None,
                        error_message=str(error),
                    )
                )

        return OrbOptimizationResult(
            runs=tuple(results)
        )
