"""ORB最適化結果の複合スコアを算出する。"""

from collections.abc import Callable

from app.backtest.composite_score_models import (
    CompositeOptimizationScore,
    CompositeOptimizationScoreReport,
    CompositeScoreComponents,
    CompositeScoreWeights,
)
from app.backtest.optimization_result_models import (
    OrbOptimizationResult,
    OrbOptimizationRunResult,
)


class CompositeOptimizationScoreService:
    """複数指標を正規化して複合スコアを算出する。"""

    def create_report(
        self,
        result: OrbOptimizationResult,
        *,
        weights: CompositeScoreWeights | None = None,
    ) -> CompositeOptimizationScoreReport:
        """正常完了した試行へ複合スコアを付与する。"""

        completed_runs = result.completed_runs

        if not completed_runs:
            return CompositeOptimizationScoreReport(
                scores=()
            )

        normalized_weights = (
            weights
            if weights is not None
            else CompositeScoreWeights()
        ).normalized

        net_profit_scores = self._normalize_metric(
            completed_runs,
            extractor=lambda run: run.net_profit_loss,
            missing_value=0.0,
        )
        profit_factor_scores = self._normalize_metric(
            completed_runs,
            extractor=lambda run: run.profit_factor,
            missing_value=0.0,
        )
        win_rate_scores = self._normalize_metric(
            completed_runs,
            extractor=lambda run: run.win_rate,
            missing_value=0.0,
        )
        drawdown_scores = self._normalize_metric(
            completed_runs,
            extractor=lambda run: run.maximum_drawdown,
            missing_value=1.0,
            inverse=True,
        )

        scores = tuple(
            self._create_score(
                run=run,
                weights=normalized_weights,
                net_profit_score=(
                    net_profit_scores[run.parameter_id]
                ),
                profit_factor_score=(
                    profit_factor_scores[run.parameter_id]
                ),
                win_rate_score=(
                    win_rate_scores[run.parameter_id]
                ),
                drawdown_score=(
                    drawdown_scores[run.parameter_id]
                ),
            )
            for run in completed_runs
        )

        return CompositeOptimizationScoreReport(
            scores=scores
        )

    @staticmethod
    def _create_score(
        *,
        run: OrbOptimizationRunResult,
        weights: CompositeScoreWeights,
        net_profit_score: float,
        profit_factor_score: float,
        win_rate_score: float,
        drawdown_score: float,
    ) -> CompositeOptimizationScore:
        """構成値と重みから1試行のスコアを作成する。"""

        components = CompositeScoreComponents(
            net_profit=net_profit_score,
            profit_factor=profit_factor_score,
            win_rate=win_rate_score,
            maximum_drawdown=drawdown_score,
        )

        raw_score = (
            components.net_profit
            * weights.net_profit
            + components.profit_factor
            * weights.profit_factor
            + components.win_rate
            * weights.win_rate
            + components.maximum_drawdown
            * weights.maximum_drawdown
        )

        score = min(1.0, max(0.0, raw_score))

        return CompositeOptimizationScore(
            run=run,
            score=score,
            components=components,
            weights=weights,
        )

    @staticmethod
    def _normalize_metric(
        runs: tuple[OrbOptimizationRunResult, ...],
        *,
        extractor: Callable[
            [OrbOptimizationRunResult],
            float | None,
        ],
        missing_value: float,
        inverse: bool = False,
    ) -> dict[str, float]:
        """指標を0〜1へMin-Max正規化する。"""

        values = {
            run.parameter_id: (
                missing_value
                if extractor(run) is None
                else float(extractor(run))
            )
            for run in runs
        }

        minimum = min(values.values())
        maximum = max(values.values())

        if maximum == minimum:
            return {
                parameter_id: 1.0
                for parameter_id in values
            }

        normalized = {
            parameter_id: min(
                1.0,
                max(
                    0.0,
                    (value - minimum)
                    / (maximum - minimum),
                ),
            )
            for parameter_id, value in values.items()
        }

        if inverse:
            normalized = {
                parameter_id: min(
                    1.0,
                    max(0.0, 1.0 - value),
                )
                for parameter_id, value in normalized.items()
            }

        return normalized
