"""Trade Journalから銘柄×戦略の学習結果を生成する。"""

from __future__ import annotations

import math
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from app.learning.strategy_learning_models import (
    StrategyLearningRecord,
    StrategyLearningReport,
    SymbolLearningRecommendation,
)
from app.learning.strategy_learning_repository import (
    StrategyLearningRepository,
)


class StrategyLearningService:
    """trade_journalを銘柄×戦略で集計する。"""

    def __init__(
        self,
        database_path: Path,
        *,
        minimum_trade_count: int = 10,
        full_confidence_trade_count: int = 30,
        now_provider: Callable[
            [],
            datetime,
        ] | None = None,
    ) -> None:
        if minimum_trade_count <= 0:
            raise ValueError(
                "最低取引数は0より大きい必要があります。"
            )
        if (
            full_confidence_trade_count
            < minimum_trade_count
        ):
            raise ValueError(
                "完全信頼取引数は最低取引数以上です。"
            )

        self.database_path = Path(database_path)
        self.minimum_trade_count = minimum_trade_count
        self.full_confidence_trade_count = (
            full_confidence_trade_count
        )
        self.now_provider = (
            now_provider
            if now_provider is not None
            else lambda: datetime.now(
                timezone.utc
            )
        )

    def analyze_and_persist(
        self,
    ) -> StrategyLearningReport:
        generated_at = self._current_time()
        rows = self._load_trade_rows()

        grouped: dict[
            tuple[str, str],
            list[dict[str, float]],
        ] = defaultdict(list)

        for row in rows:
            grouped[
                (
                    str(row["code"]),
                    str(row["strategy_name"]),
                )
            ].append(row)

        records = tuple(
            sorted(
                (
                    self._build_record(
                        code=code,
                        strategy_name=strategy_name,
                        values=values,
                        updated_at=generated_at,
                    )
                    for (
                        code,
                        strategy_name,
                    ), values in grouped.items()
                ),
                key=lambda item: (
                    item.code,
                    -item.historical_score,
                    item.strategy_name,
                ),
            )
        )

        recommendations = self._recommend(
            records
        )

        StrategyLearningRepository(
            self.database_path
        ).replace_all(records)

        return StrategyLearningReport(
            generated_at=generated_at,
            minimum_trade_count=(
                self.minimum_trade_count
            ),
            record_count=len(records),
            recommendation_count=len(
                recommendations
            ),
            records=records,
            recommendations=recommendations,
        )

    def _load_trade_rows(
        self,
    ) -> tuple[dict[str, float], ...]:
        if not self.database_path.exists():
            return ()

        with sqlite3.connect(
            self.database_path
        ) as connection:
            if not self._table_exists(
                connection,
                "trade_journal",
            ):
                return ()

            rows = connection.execute(
                """
                SELECT
                    code,
                    strategy_name,
                    realized_profit_loss,
                    return_rate,
                    holding_minutes
                FROM trade_journal
                ORDER BY exit_at ASC, id ASC
                """
            ).fetchall()

        return tuple(
            {
                "code": str(row[0]),
                "strategy_name": str(row[1]),
                "profit_loss": float(row[2]),
                "return_rate": float(row[3]),
                "holding_minutes": float(row[4]),
            }
            for row in rows
        )

    def _build_record(
        self,
        *,
        code: str,
        strategy_name: str,
        values: list[dict[str, float]],
        updated_at: datetime,
    ) -> StrategyLearningRecord:
        wins = [
            item
            for item in values
            if item["profit_loss"] > 0
        ]
        losses = [
            item
            for item in values
            if item["profit_loss"] < 0
        ]
        trade_count = len(values)
        breakeven_count = (
            trade_count
            - len(wins)
            - len(losses)
        )
        gross_profit = sum(
            item["profit_loss"]
            for item in wins
        )
        gross_loss = sum(
            item["profit_loss"]
            for item in losses
        )
        profit_factor = (
            gross_profit / abs(gross_loss)
            if gross_loss < 0
            else (
                float("inf")
                if gross_profit > 0
                else None
            )
        )
        expectancy = self._average(
            [
                item["profit_loss"]
                for item in values
            ]
        )
        win_rate = (
            len(wins) / trade_count
            if trade_count > 0
            else None
        )
        confidence = min(
            1.0,
            trade_count
            / self.full_confidence_trade_count,
        )
        raw_score = self._raw_historical_score(
            trade_count=trade_count,
            win_rate=win_rate,
            profit_factor=profit_factor,
            expectancy=expectancy,
        )
        historical_score = round(
            raw_score * confidence,
            4,
        )

        return StrategyLearningRecord(
            code=code,
            strategy_name=strategy_name,
            trade_count=trade_count,
            win_count=len(wins),
            loss_count=len(losses),
            breakeven_count=breakeven_count,
            win_rate=win_rate,
            gross_profit=gross_profit,
            gross_loss=gross_loss,
            net_profit_loss=sum(
                item["profit_loss"]
                for item in values
            ),
            profit_factor=profit_factor,
            expectancy=expectancy,
            average_return_rate=self._average(
                [
                    item["return_rate"]
                    for item in values
                ]
            ),
            average_holding_minutes=self._average(
                [
                    item["holding_minutes"]
                    for item in values
                ]
            ),
            sample_confidence=confidence,
            historical_score=historical_score,
            eligible_for_feedback=(
                trade_count
                >= self.minimum_trade_count
            ),
            updated_at=updated_at,
        )

    def _recommend(
        self,
        records: tuple[
            StrategyLearningRecord,
            ...,
        ],
    ) -> tuple[
        SymbolLearningRecommendation,
        ...,
    ]:
        grouped: dict[
            str,
            list[StrategyLearningRecord],
        ] = defaultdict(list)

        for record in records:
            grouped[record.code].append(record)

        recommendations = []

        for code, candidates in grouped.items():
            eligible = [
                item
                for item in candidates
                if item.eligible_for_feedback
            ]
            ordered = tuple(
                sorted(
                    candidates,
                    key=lambda item: (
                        -item.historical_score,
                        -item.trade_count,
                        item.strategy_name,
                    ),
                )
            )

            if not eligible:
                preferred = None
                reason = (
                    "Minimum trade count has not "
                    "been reached."
                )
            else:
                best = max(
                    eligible,
                    key=lambda item: (
                        item.historical_score,
                        item.expectancy
                        if item.expectancy is not None
                        else float("-inf"),
                        item.trade_count,
                    ),
                )
                preferred = best.strategy_name
                reason = (
                    "Highest eligible historical score. "
                    f"score={best.historical_score:.2f} "
                    f"trades={best.trade_count}"
                )

            recommendations.append(
                SymbolLearningRecommendation(
                    code=code,
                    preferred_strategy=preferred,
                    eligible_strategy_count=len(
                        eligible
                    ),
                    reason=reason,
                    candidates=ordered,
                )
            )

        return tuple(
            sorted(
                recommendations,
                key=lambda item: item.code,
            )
        )

    @staticmethod
    def _raw_historical_score(
        *,
        trade_count: int,
        win_rate: float | None,
        profit_factor: float | None,
        expectancy: float | None,
    ) -> float:
        if trade_count <= 0:
            return 0.0

        win_component = min(
            6.0,
            max(
                0.0,
                ((win_rate or 0.0) - 0.40)
                / 0.30
                * 6.0,
            ),
        )

        if (
            profit_factor is not None
            and math.isinf(profit_factor)
        ):
            pf_component = 8.0
        else:
            pf_component = min(
                8.0,
                max(
                    0.0,
                    ((profit_factor or 0.0) - 0.8)
                    / 1.2
                    * 8.0,
                ),
            )

        expectancy_component = min(
            4.0,
            max(
                0.0,
                (expectancy or 0.0)
                / 5_000.0
                * 4.0,
            ),
        )
        sample_component = min(
            2.0,
            trade_count / 20.0 * 2.0,
        )

        return min(
            20.0,
            win_component
            + pf_component
            + expectancy_component
            + sample_component,
        )

    @staticmethod
    def _average(
        values: list[float],
    ) -> float | None:
        if not values:
            return None
        return sum(values) / len(values)

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

    def _current_time(self) -> datetime:
        value = self.now_provider()

        if value.tzinfo is None:
            raise ValueError(
                "現在日時にはタイムゾーンが必要です。"
            )

        return value.astimezone(
            timezone.utc
        )
