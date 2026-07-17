"""ORB最適化の複合スコアモデル。"""

from dataclasses import dataclass

from app.backtest.optimization_result_models import (
    OrbOptimizationRunResult,
)


@dataclass(frozen=True, slots=True)
class CompositeScoreWeights:
    """複合スコアに使用する指標別の重み。"""

    net_profit: float = 0.4
    profit_factor: float = 0.3
    win_rate: float = 0.2
    maximum_drawdown: float = 0.1

    def __post_init__(self) -> None:
        """重みを検証する。"""

        values = {
            "純損益": self.net_profit,
            "Profit Factor": self.profit_factor,
            "勝率": self.win_rate,
            "最大ドローダウン": self.maximum_drawdown,
        }

        for name, value in values.items():
            if value < 0:
                raise ValueError(
                    f"{name}の重みは0以上である必要があります。"
                )

        if self.total <= 0:
            raise ValueError(
                "複合スコアの重み合計は"
                "0より大きい必要があります。"
            )

    @property
    def total(self) -> float:
        """重み合計を返す。"""

        return (
            self.net_profit
            + self.profit_factor
            + self.win_rate
            + self.maximum_drawdown
        )

    @property
    def normalized(self) -> CompositeScoreWeights:
        """合計1.0へ正規化した重みを返す。"""

        total = self.total

        return CompositeScoreWeights(
            net_profit=self.net_profit / total,
            profit_factor=self.profit_factor / total,
            win_rate=self.win_rate / total,
            maximum_drawdown=(
                self.maximum_drawdown / total
            ),
        )


@dataclass(frozen=True, slots=True)
class CompositeScoreComponents:
    """複合スコアを構成する正規化済み指標。"""

    net_profit: float
    profit_factor: float
    win_rate: float
    maximum_drawdown: float

    def __post_init__(self) -> None:
        """各構成値が0以上1以下か検証する。"""

        for name, value in {
            "純損益スコア": self.net_profit,
            "Profit Factorスコア": self.profit_factor,
            "勝率スコア": self.win_rate,
            "最大ドローダウンスコア": (
                self.maximum_drawdown
            ),
        }.items():
            if not 0.0 <= value <= 1.0:
                raise ValueError(
                    f"{name}は0以上1以下である必要があります。"
                )


@dataclass(frozen=True, slots=True)
class CompositeOptimizationScore:
    """1試行の複合スコア。"""

    run: OrbOptimizationRunResult
    score: float
    components: CompositeScoreComponents
    weights: CompositeScoreWeights

    def __post_init__(self) -> None:
        """複合スコアを検証する。"""

        if not 0.0 <= self.score <= 1.0:
            raise ValueError(
                "複合スコアは0以上1以下である必要があります。"
            )

        if not self.run.is_completed:
            raise ValueError(
                "複合スコアは正常完了した試行だけに"
                "設定できます。"
            )

    @property
    def parameter_id(self) -> str:
        """パラメータIDを返す。"""

        return self.run.parameter_id


@dataclass(frozen=True, slots=True)
class CompositeOptimizationScoreReport:
    """最適化結果全体の複合スコア一覧。"""

    scores: tuple[CompositeOptimizationScore, ...]

    def __post_init__(self) -> None:
        """パラメータID重複を拒否する。"""

        parameter_ids = [
            item.parameter_id
            for item in self.scores
        ]

        if len(parameter_ids) != len(set(parameter_ids)):
            raise ValueError(
                "複合スコアのパラメータIDが"
                "重複しています。"
            )

    @property
    def score_count(self) -> int:
        """スコア件数を返す。"""

        return len(self.scores)

    def get(
        self,
        parameter_id: str,
    ) -> CompositeOptimizationScore:
        """パラメータIDに一致するスコアを返す。"""

        normalized = parameter_id.strip()

        if not normalized:
            raise ValueError(
                "パラメータIDを指定してください。"
            )

        for item in self.scores:
            if item.parameter_id == normalized:
                return item

        raise KeyError(
            "指定された複合スコアが存在しません。 "
            f"parameter_id={normalized}"
        )
