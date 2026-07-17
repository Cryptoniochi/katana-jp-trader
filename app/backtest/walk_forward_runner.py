"""Walk-Forward Optimizationの実行中核。"""

from __future__ import annotations

from collections.abc import Callable

from app.backtest.composite_ranking import (
    CompositeOptimizationRankingService,
)
from app.backtest.composite_score_models import (
    CompositeScoreWeights,
)
from app.backtest.composite_score_service import (
    CompositeOptimizationScoreService,
)
from app.backtest.historical_models import (
    HistoricalBarSeries,
)
from app.backtest.optimization_models import (
    OrbOptimizationGrid,
    OrbOptimizationParameters,
)
from app.backtest.optimization_ranking import (
    OptimizationRankingService,
    RankingMetric,
)
from app.backtest.optimization_report_writer import (
    OptimizationReportWriter,
)
from app.backtest.optimization_runner import (
    OrbOptimizationExecutionOutput,
    OrbOptimizationRunner,
)
from app.backtest.walk_forward_models import (
    WalkForwardWindow,
    WalkForwardWindowPlan,
)
from app.backtest.walk_forward_result_models import (
    WalkForwardResult,
    WalkForwardValidationResult,
    WalkForwardWindowResult,
    WalkForwardWindowStatus,
)


COMPOSITE_RANKING = "composite"

WalkForwardExecutor = Callable[
    [
        HistoricalBarSeries,
        OrbOptimizationParameters,
    ],
    OrbOptimizationExecutionOutput,
]


class WalkForwardRunner:
    """各学習期間で最適化し、次の検証期間へ適用する。"""

    def __init__(
        self,
        *,
        training_executor: WalkForwardExecutor,
        validation_executor: WalkForwardExecutor,
    ) -> None:
        """学習・検証バックテスト実行処理を設定する。"""

        self.training_executor = training_executor
        self.validation_executor = validation_executor

    def run(
        self,
        plan: WalkForwardWindowPlan,
        *,
        grid: OrbOptimizationGrid,
        ranking_method: str = RankingMetric.NET_PROFIT.value,
        composite_weights: CompositeScoreWeights | None = None,
        continue_on_error: bool = False,
    ) -> WalkForwardResult:
        """プラン内の全ウィンドウを順番に実行する。"""

        normalized_method = ranking_method.strip().lower()

        if not normalized_method:
            raise ValueError(
                "ranking_methodを指定してください。"
            )

        if (
            normalized_method != COMPOSITE_RANKING
            and normalized_method
            not in {
                metric.value
                for metric in RankingMetric
            }
        ):
            raise ValueError(
                "未対応のranking_methodです。 "
                f"ranking_method={normalized_method}"
            )

        results: list[WalkForwardWindowResult] = []

        for window in plan.windows:
            try:
                result = self._run_window(
                    window,
                    grid=grid,
                    ranking_method=normalized_method,
                    composite_weights=composite_weights,
                )
            except Exception as error:
                if not continue_on_error:
                    raise

                result = WalkForwardWindowResult(
                    window=window,
                    status=WalkForwardWindowStatus.FAILED,
                    ranking_method=normalized_method,
                    optimization_result=None,
                    best_training_run=None,
                    best_training_score=None,
                    validation_result=None,
                    composite_score_report=None,
                    error_message=str(error),
                )

            results.append(result)

        return WalkForwardResult(
            plan=plan,
            window_results=tuple(results),
        )

    def _run_window(
        self,
        window: WalkForwardWindow,
        *,
        grid: OrbOptimizationGrid,
        ranking_method: str,
        composite_weights: CompositeScoreWeights | None,
    ) -> WalkForwardWindowResult:
        """1ウィンドウの学習・選択・検証を実行する。"""

        optimization_result = OrbOptimizationRunner(
            executor=lambda parameter: (
                self.training_executor(
                    window.training_series,
                    parameter,
                )
            )
        ).run(
            grid,
            continue_on_error=True,
        )

        composite_score_report = None

        if ranking_method == COMPOSITE_RANKING:
            composite_score_report = (
                CompositeOptimizationScoreService()
                .create_report(
                    optimization_result,
                    weights=composite_weights,
                )
            )
            ranking = (
                CompositeOptimizationRankingService()
                .rank(
                    composite_score_report,
                    top_n=1,
                )
            )
        else:
            ranking = OptimizationRankingService().rank(
                optimization_result,
                metric=RankingMetric(ranking_method),
                top_n=1,
            )

        best_training_run = (
            OptimizationReportWriter.best_run(
                ranking
            )
        )

        if best_training_run is None:
            raise RuntimeError(
                "正常完了した学習試行がないため、"
                "検証期間へ適用するパラメータを選択できません。 "
                f"window_id={window.window_id}"
            )

        best_training_score = (
            OptimizationReportWriter.best_score(
                ranking,
                ranking_method=ranking_method,
            )
        )

        validation_output = self.validation_executor(
            window.validation_series,
            best_training_run.parameter,
        )
        validation_result = WalkForwardValidationResult(
            parameter=best_training_run.parameter,
            metrics=validation_output.metrics,
            equity_curve_report=(
                validation_output.equity_curve_report
            ),
        )

        return WalkForwardWindowResult(
            window=window,
            status=WalkForwardWindowStatus.COMPLETED,
            ranking_method=ranking_method,
            optimization_result=optimization_result,
            best_training_run=best_training_run,
            best_training_score=best_training_score,
            validation_result=validation_result,
            composite_score_report=composite_score_report,
            error_message=None,
        )
