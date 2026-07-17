"""ORB最適化実行結果の共通モデル。"""

from dataclasses import dataclass
from enum import StrEnum

from app.backtest.optimization_models import (
    OrbOptimizationParameters,
)
from app.backtest.performance_metrics_models import (
    BacktestPerformanceMetrics,
)
from app.trading.equity_curve_models import (
    EquityCurveReport,
)


class OptimizationRunStatus(StrEnum):
    """1試行の終了状態。"""

    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class OrbOptimizationRunResult:
    """1つのパラメータ組み合わせの実行結果。"""

    parameter: OrbOptimizationParameters
    status: OptimizationRunStatus
    metrics: BacktestPerformanceMetrics | None
    equity_curve_report: EquityCurveReport | None
    error_message: str | None = None

    def __post_init__(self) -> None:
        """実行結果の整合性を検証する。"""

        if self.status is OptimizationRunStatus.COMPLETED:
            if self.metrics is None:
                raise ValueError(
                    "完了結果には成績指標が必要です。"
                )

            if self.error_message is not None:
                raise ValueError(
                    "完了結果にはエラーメッセージを"
                    "設定できません。"
                )

        if self.status is OptimizationRunStatus.FAILED:
            if not (self.error_message or "").strip():
                raise ValueError(
                    "失敗結果にはエラーメッセージが必要です。"
                )

    @property
    def parameter_id(self) -> str:
        """パラメータIDを返す。"""

        return self.parameter.parameter_id

    @property
    def is_completed(self) -> bool:
        """正常完了したか返す。"""

        return self.status is OptimizationRunStatus.COMPLETED

    @property
    def is_failed(self) -> bool:
        """失敗したか返す。"""

        return self.status is OptimizationRunStatus.FAILED

    @property
    def net_profit_loss(self) -> float | None:
        """純損益を返す。"""

        if self.metrics is None:
            return None

        return self.metrics.net_profit_loss

    @property
    def profit_factor(self) -> float | None:
        """Profit Factorを返す。"""

        if self.metrics is None:
            return None

        return self.metrics.profit_factor

    @property
    def win_rate(self) -> float | None:
        """勝率を返す。"""

        if self.metrics is None:
            return None

        return self.metrics.win_rate

    @property
    def maximum_drawdown(self) -> float | None:
        """最大ドローダウン率を返す。"""

        if self.equity_curve_report is None:
            return None

        return self.equity_curve_report.maximum_drawdown


@dataclass(frozen=True, slots=True)
class OrbOptimizationResult:
    """最適化グリッド全体の実行結果。"""

    runs: tuple[OrbOptimizationRunResult, ...]

    def __post_init__(self) -> None:
        """パラメータIDの重複を拒否する。"""

        parameter_ids = [
            run.parameter_id
            for run in self.runs
        ]

        if len(parameter_ids) != len(set(parameter_ids)):
            raise ValueError(
                "最適化実行結果のパラメータIDが"
                "重複しています。"
            )

    @property
    def run_count(self) -> int:
        """試行件数を返す。"""

        return len(self.runs)

    @property
    def completed_count(self) -> int:
        """正常完了件数を返す。"""

        return sum(
            run.is_completed
            for run in self.runs
        )

    @property
    def failed_count(self) -> int:
        """失敗件数を返す。"""

        return sum(
            run.is_failed
            for run in self.runs
        )

    @property
    def completed_runs(
        self,
    ) -> tuple[OrbOptimizationRunResult, ...]:
        """正常完了した試行だけ返す。"""

        return tuple(
            run
            for run in self.runs
            if run.is_completed
        )

    @property
    def failed_runs(
        self,
    ) -> tuple[OrbOptimizationRunResult, ...]:
        """失敗した試行だけ返す。"""

        return tuple(
            run
            for run in self.runs
            if run.is_failed
        )

    def get(
        self,
        parameter_id: str,
    ) -> OrbOptimizationRunResult:
        """パラメータIDに一致する結果を返す。"""

        normalized = parameter_id.strip()

        if not normalized:
            raise ValueError(
                "パラメータIDを指定してください。"
            )

        for run in self.runs:
            if run.parameter_id == normalized:
                return run

        raise KeyError(
            "指定された最適化結果が存在しません。 "
            f"parameter_id={normalized}"
        )
