"""Walk-Forward Optimization実行結果の共通モデル。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.backtest.composite_score_models import (
    CompositeOptimizationScoreReport,
)
from app.backtest.optimization_models import (
    OrbOptimizationParameters,
)
from app.backtest.optimization_result_models import (
    OrbOptimizationResult,
    OrbOptimizationRunResult,
)
from app.backtest.performance_metrics_models import (
    BacktestPerformanceMetrics,
)
from app.backtest.walk_forward_models import (
    WalkForwardWindow,
    WalkForwardWindowPlan,
)
from app.trading.equity_curve_models import (
    EquityCurveReport,
)


class WalkForwardWindowStatus(StrEnum):
    """Walk-Forwardウィンドウの終了状態。"""

    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class WalkForwardValidationResult:
    """最良パラメータによる検証期間の実行結果。"""

    parameter: OrbOptimizationParameters
    metrics: BacktestPerformanceMetrics
    equity_curve_report: EquityCurveReport | None

    @property
    def parameter_id(self) -> str:
        """適用したパラメータIDを返す。"""

        return self.parameter.parameter_id


@dataclass(frozen=True, slots=True)
class WalkForwardWindowResult:
    """1ウィンドウ分の学習・選択・検証結果。"""

    window: WalkForwardWindow
    status: WalkForwardWindowStatus
    ranking_method: str
    optimization_result: OrbOptimizationResult | None
    best_training_run: OrbOptimizationRunResult | None
    best_training_score: float | None
    validation_result: WalkForwardValidationResult | None
    composite_score_report: (
        CompositeOptimizationScoreReport | None
    ) = None
    error_message: str | None = None

    def __post_init__(self) -> None:
        """状態と保持データの整合性を検証する。"""

        normalized_method = self.ranking_method.strip().lower()

        if not normalized_method:
            raise ValueError(
                "ranking_methodを指定してください。"
            )

        object.__setattr__(
            self,
            "ranking_method",
            normalized_method,
        )

        if self.status is WalkForwardWindowStatus.COMPLETED:
            if self.optimization_result is None:
                raise ValueError(
                    "完了結果には最適化結果が必要です。"
                )

            if self.best_training_run is None:
                raise ValueError(
                    "完了結果には最良学習結果が必要です。"
                )

            if self.validation_result is None:
                raise ValueError(
                    "完了結果には検証結果が必要です。"
                )

            if self.error_message is not None:
                raise ValueError(
                    "完了結果にはエラーメッセージを"
                    "設定できません。"
                )

            if (
                self.best_training_run.parameter
                != self.validation_result.parameter
            ):
                raise ValueError(
                    "学習期間で選択したパラメータと"
                    "検証期間へ適用したパラメータが一致しません。"
                )

        if self.status is WalkForwardWindowStatus.FAILED:
            if not (self.error_message or "").strip():
                raise ValueError(
                    "失敗結果にはエラーメッセージが必要です。"
                )

            if self.validation_result is not None:
                raise ValueError(
                    "失敗結果には検証結果を設定できません。"
                )

    @property
    def window_id(self) -> str:
        """ウィンドウIDを返す。"""

        return self.window.window_id

    @property
    def is_completed(self) -> bool:
        """正常完了したか返す。"""

        return self.status is WalkForwardWindowStatus.COMPLETED

    @property
    def is_failed(self) -> bool:
        """失敗したか返す。"""

        return self.status is WalkForwardWindowStatus.FAILED

    @property
    def selected_parameter(
        self,
    ) -> OrbOptimizationParameters | None:
        """採用パラメータを返す。"""

        if self.best_training_run is None:
            return None

        return self.best_training_run.parameter


@dataclass(frozen=True, slots=True)
class WalkForwardResult:
    """Walk-Forward全ウィンドウの実行結果。"""

    plan: WalkForwardWindowPlan
    window_results: tuple[
        WalkForwardWindowResult,
        ...
    ]

    def __post_init__(self) -> None:
        """プランと実行結果の対応を検証する。"""

        expected_ids = [
            window.window_id
            for window in self.plan.windows
        ]
        actual_ids = [
            result.window_id
            for result in self.window_results
        ]

        if actual_ids != expected_ids:
            raise ValueError(
                "Walk-Forward実行結果はプランの"
                "ウィンドウ順と一致する必要があります。"
            )

    @property
    def window_count(self) -> int:
        """実行対象ウィンドウ件数を返す。"""

        return len(self.window_results)

    @property
    def completed_count(self) -> int:
        """正常完了件数を返す。"""

        return sum(
            result.is_completed
            for result in self.window_results
        )

    @property
    def failed_count(self) -> int:
        """失敗件数を返す。"""

        return sum(
            result.is_failed
            for result in self.window_results
        )

    @property
    def completed_results(
        self,
    ) -> tuple[WalkForwardWindowResult, ...]:
        """正常完了したウィンドウ結果だけ返す。"""

        return tuple(
            result
            for result in self.window_results
            if result.is_completed
        )

    @property
    def failed_results(
        self,
    ) -> tuple[WalkForwardWindowResult, ...]:
        """失敗したウィンドウ結果だけ返す。"""

        return tuple(
            result
            for result in self.window_results
            if result.is_failed
        )

    def get(
        self,
        window_id: str,
    ) -> WalkForwardWindowResult:
        """ウィンドウIDに一致する結果を返す。"""

        normalized = window_id.strip()

        if not normalized:
            raise ValueError(
                "ウィンドウIDを指定してください。"
            )

        for result in self.window_results:
            if result.window_id == normalized:
                return result

        raise KeyError(
            "指定されたWalk-Forward実行結果が存在しません。 "
            f"window_id={normalized}"
        )
