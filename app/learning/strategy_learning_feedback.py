"""Strategy Learning結果をWatchlist向けに提供する。"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path


STRATEGY_NAME_ALIASES = {
    "opening-range-breakout-v2": "orb",
    "orb": "orb",
    "pullback-breakout-v1": "pullback",
    "pullback": "pullback",
    "high-breakout-v1": "high-breakout",
    "high-breakout": "high-breakout",
}


@dataclass(frozen=True, slots=True)
class StrategyLearningFeedback:
    """1戦略に適用できる学習フィードバック。"""

    code: str
    strategy_name: str
    source_strategy_name: str
    trade_count: int
    historical_score: float
    sample_confidence: float


@dataclass(frozen=True, slots=True)
class SymbolLearningFeedback:
    """1銘柄の利用可能な学習結果。"""

    code: str
    strategies: tuple[StrategyLearningFeedback, ...]

    def for_strategy(
        self,
        strategy_name: str,
    ) -> StrategyLearningFeedback | None:
        normalized = STRATEGY_NAME_ALIASES.get(
            strategy_name,
            strategy_name,
        )
        for item in self.strategies:
            if item.strategy_name == normalized:
                return item
        return None

    @property
    def best(self) -> StrategyLearningFeedback | None:
        if not self.strategies:
            return None
        return max(
            self.strategies,
            key=lambda item: (
                item.historical_score,
                item.trade_count,
                item.strategy_name,
            ),
        )


class StrategyLearningFeedbackProvider:
    """SQLiteの学習サマリーを安全に読み込む。"""

    def __init__(
        self,
        database_path: Path,
    ) -> None:
        self.database_path = Path(database_path)
        self._cache: dict[
            str,
            SymbolLearningFeedback,
        ] | None = None

    def load_all(
        self,
    ) -> dict[str, SymbolLearningFeedback]:
        if self._cache is not None:
            return self._cache

        grouped: dict[
            str,
            list[StrategyLearningFeedback],
        ] = {}

        if not self.database_path.exists():
            self._cache = {}
            return self._cache

        with sqlite3.connect(
            self.database_path
        ) as connection:
            if not self._table_exists(
                connection,
                "strategy_learning_summary",
            ):
                self._cache = {}
                return self._cache

            rows = connection.execute(
                """
                SELECT
                    code,
                    strategy_name,
                    trade_count,
                    historical_score,
                    sample_confidence
                FROM strategy_learning_summary
                WHERE eligible_for_feedback = 1
                ORDER BY code ASC,
                         historical_score DESC,
                         trade_count DESC
                """
            ).fetchall()

        for row in rows:
            source_name = str(row[1]).strip()
            strategy_name = STRATEGY_NAME_ALIASES.get(
                source_name
            )
            if strategy_name is None:
                continue

            code = str(row[0]).strip()
            grouped.setdefault(code, []).append(
                StrategyLearningFeedback(
                    code=code,
                    strategy_name=strategy_name,
                    source_strategy_name=source_name,
                    trade_count=int(row[2]),
                    historical_score=max(
                        0.0,
                        min(20.0, float(row[3])),
                    ),
                    sample_confidence=max(
                        0.0,
                        min(1.0, float(row[4])),
                    ),
                )
            )

        self._cache = {
            code: SymbolLearningFeedback(
                code=code,
                strategies=tuple(values),
            )
            for code, values in grouped.items()
        }
        return self._cache

    def for_code(
        self,
        code: str,
    ) -> SymbolLearningFeedback | None:
        return self.load_all().get(
            code.strip()
        )

    @staticmethod
    def _table_exists(
        connection: sqlite3.Connection,
        table_name: str,
    ) -> bool:
        row = connection.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type = 'table'
              AND name = ?
            """,
            (table_name,),
        ).fetchone()
        return row is not None
