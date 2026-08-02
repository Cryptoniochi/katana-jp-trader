"""銘柄×戦略の学習結果モデル。"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class StrategyLearningRecord:
    """1銘柄・1戦略の集計済み学習結果。"""

    code: str
    strategy_name: str
    trade_count: int
    win_count: int
    loss_count: int
    breakeven_count: int
    win_rate: float | None
    gross_profit: float
    gross_loss: float
    net_profit_loss: float
    profit_factor: float | None
    expectancy: float | None
    average_return_rate: float | None
    average_holding_minutes: float | None
    sample_confidence: float
    historical_score: float
    eligible_for_feedback: bool
    updated_at: datetime

    def __post_init__(self) -> None:
        if not self.code.strip():
            raise ValueError("銘柄コードを指定してください。")
        if not self.strategy_name.strip():
            raise ValueError("戦略名を指定してください。")
        if self.trade_count < 0:
            raise ValueError("取引数は0以上である必要があります。")
        if (
            self.win_count
            + self.loss_count
            + self.breakeven_count
            != self.trade_count
        ):
            raise ValueError(
                "勝敗件数の合計が取引数と一致しません。"
            )
        if not 0.0 <= self.sample_confidence <= 1.0:
            raise ValueError(
                "サンプル信頼度は0以上1以下です。"
            )
        if not 0.0 <= self.historical_score <= 20.0:
            raise ValueError(
                "履歴スコアは0以上20以下です。"
            )
        if self.updated_at.tzinfo is None:
            raise ValueError(
                "更新日時にはタイムゾーンが必要です。"
            )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["updated_at"] = self.updated_at.isoformat()
        return payload


@dataclass(frozen=True, slots=True)
class SymbolLearningRecommendation:
    """1銘柄の推奨戦略。"""

    code: str
    preferred_strategy: str | None
    eligible_strategy_count: int
    reason: str
    candidates: tuple[StrategyLearningRecord, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "preferred_strategy": self.preferred_strategy,
            "eligible_strategy_count": self.eligible_strategy_count,
            "reason": self.reason,
            "candidates": [
                item.to_dict()
                for item in self.candidates
            ],
        }


@dataclass(frozen=True, slots=True)
class StrategyLearningReport:
    """学習処理全体の結果。"""

    generated_at: datetime
    minimum_trade_count: int
    record_count: int
    recommendation_count: int
    records: tuple[StrategyLearningRecord, ...]
    recommendations: tuple[SymbolLearningRecommendation, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at.isoformat(),
            "minimum_trade_count": self.minimum_trade_count,
            "record_count": self.record_count,
            "recommendation_count": self.recommendation_count,
            "records": [
                item.to_dict()
                for item in self.records
            ],
            "recommendations": [
                item.to_dict()
                for item in self.recommendations
            ],
        }
