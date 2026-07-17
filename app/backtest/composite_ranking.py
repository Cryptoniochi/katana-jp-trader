"""複合最適化スコアのランキング。"""

from dataclasses import dataclass

from app.backtest.composite_score_models import (
    CompositeOptimizationScore,
    CompositeOptimizationScoreReport,
)


@dataclass(frozen=True, slots=True)
class RankedCompositeOptimizationScore:
    """順位付き複合スコア。"""

    rank: int
    item: CompositeOptimizationScore

    def __post_init__(self) -> None:
        """順位を検証する。"""

        if self.rank <= 0:
            raise ValueError(
                "順位は0より大きい必要があります。"
            )

    @property
    def parameter_id(self) -> str:
        """パラメータIDを返す。"""

        return self.item.parameter_id

    @property
    def score(self) -> float:
        """複合スコアを返す。"""

        return self.item.score


@dataclass(frozen=True, slots=True)
class CompositeOptimizationRanking:
    """複合スコア順のランキング。"""

    items: tuple[RankedCompositeOptimizationScore, ...]

    def __post_init__(self) -> None:
        """順位とパラメータIDの重複を検証する。"""

        ranks = [
            item.rank
            for item in self.items
        ]
        parameter_ids = [
            item.parameter_id
            for item in self.items
        ]

        if len(ranks) != len(set(ranks)):
            raise ValueError(
                "ランキングの順位が重複しています。"
            )

        if len(parameter_ids) != len(set(parameter_ids)):
            raise ValueError(
                "ランキングのパラメータIDが"
                "重複しています。"
            )

        expected_ranks = list(
            range(1, len(self.items) + 1)
        )

        if ranks != expected_ranks:
            raise ValueError(
                "ランキングの順位は1からの連番で"
                "指定してください。"
            )

    @property
    def item_count(self) -> int:
        """ランキング件数を返す。"""

        return len(self.items)

    @property
    def best(
        self,
    ) -> RankedCompositeOptimizationScore | None:
        """最上位結果を返す。"""

        if not self.items:
            return None

        return self.items[0]

    def get(
        self,
        parameter_id: str,
    ) -> RankedCompositeOptimizationScore:
        """パラメータIDに一致する順位結果を返す。"""

        normalized = parameter_id.strip()

        if not normalized:
            raise ValueError(
                "パラメータIDを指定してください。"
            )

        for item in self.items:
            if item.parameter_id == normalized:
                return item

        raise KeyError(
            "指定されたランキング結果が存在しません。 "
            f"parameter_id={normalized}"
        )


class CompositeOptimizationRankingService:
    """複合スコア一覧を順位付けする。"""

    def rank(
        self,
        report: CompositeOptimizationScoreReport,
        *,
        top_n: int | None = None,
    ) -> CompositeOptimizationRanking:
        """スコア降順で安定したランキングを返す。"""

        if top_n is not None and top_n <= 0:
            raise ValueError(
                "top_nは0より大きい必要があります。"
            )

        ordered = sorted(
            report.scores,
            key=lambda item: (
                -item.score,
                item.parameter_id,
            ),
        )

        if top_n is not None:
            ordered = ordered[:top_n]

        items = tuple(
            RankedCompositeOptimizationScore(
                rank=index,
                item=item,
            )
            for index, item in enumerate(
                ordered,
                start=1,
            )
        )

        return CompositeOptimizationRanking(
            items=items
        )
