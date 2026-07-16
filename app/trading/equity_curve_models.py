"""資産曲線と運用成績の共通データモデル。"""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class EquityCurvePoint:
    """ある時点の純資産と損益情報。"""

    generated_at: datetime
    equity: float
    cash_balance: float
    market_value: float
    realized_profit_loss: float
    unrealized_profit_loss: float
    period_return: float | None
    cumulative_return: float

    def __post_init__(self) -> None:
        """資産曲線データを検証する。"""

        if self.generated_at.tzinfo is None:
            raise ValueError(
                "集計日時にはタイムゾーンが必要です。"
            )

        if self.equity < 0:
            raise ValueError(
                "純資産額は0以上である必要があります。"
            )

        if self.cash_balance < 0:
            raise ValueError(
                "現金残高は0以上である必要があります。"
            )

        if self.market_value < 0:
            raise ValueError(
                "評価額は0以上である必要があります。"
            )


@dataclass(frozen=True, slots=True)
class EquityCurveReport:
    """ポートフォリオ履歴から算出した運用成績。"""

    points: tuple[
        EquityCurvePoint,
        ...
    ]
    initial_equity: float
    final_equity: float
    absolute_profit_loss: float
    total_return: float
    maximum_drawdown: float
    maximum_drawdown_amount: float
    winning_period_count: int
    losing_period_count: int
    flat_period_count: int

    def __post_init__(self) -> None:
        """運用成績の整合性を検証する。"""

        if self.initial_equity < 0:
            raise ValueError(
                "初期純資産は0以上である必要があります。"
            )

        if self.final_equity < 0:
            raise ValueError(
                "最終純資産は0以上である必要があります。"
            )

        if not 0.0 <= self.maximum_drawdown <= 1.0:
            raise ValueError(
                "最大ドローダウン率は0以上1以下である必要があります。"
            )

        if self.maximum_drawdown_amount < 0:
            raise ValueError(
                "最大ドローダウン額は0以上である必要があります。"
            )

        for name, value in {
            "勝ち期間数": self.winning_period_count,
            "負け期間数": self.losing_period_count,
            "横ばい期間数": self.flat_period_count,
        }.items():
            if value < 0:
                raise ValueError(
                    f"{name}は0以上である必要があります。"
                )

    @property
    def point_count(self) -> int:
        """資産曲線のデータ点数を返す。"""

        return len(self.points)

    @property
    def period_count(self) -> int:
        """収益率を計算できる期間数を返す。"""

        return max(0, self.point_count - 1)

    @property
    def winning_period_rate(self) -> float | None:
        """値動きのあった期間に対する勝ち期間比率を返す。"""

        decided_periods = (
            self.winning_period_count
            + self.losing_period_count
        )

        if decided_periods == 0:
            return None

        return self.winning_period_count / decided_periods
