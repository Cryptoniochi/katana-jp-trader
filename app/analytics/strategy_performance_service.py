"""Trade Journalから戦略成績を集計する。"""

from __future__ import annotations

import math
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from app.analytics.strategy_performance_models import (
    StrategyPerformance,
    StrategyPerformancePayload,
)


class StrategyPerformanceAnalyzer:
    """trade_journalを戦略単位で集計・順位付けする。"""

    DISPLAY_NAMES = {
        "opening-range-breakout-v2": "ORB",
        "pullback-breakout-v1": "Pullback",
        "high-breakout-v1": "High Breakout",
    }

    def __init__(
        self,
        database_path: Path,
        *,
        now_provider=None,
    ) -> None:
        self.database_path = Path(database_path)
        self.now_provider = (
            now_provider
            if now_provider is not None
            else lambda: datetime.now(timezone.utc)
        )

    def analyze(
        self,
        *,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
    ) -> StrategyPerformancePayload:
        """指定期間の成績をスコア順で返す。"""

        if (
            start_at is not None
            and start_at.tzinfo is None
        ):
            raise ValueError(
                "開始日時にはタイムゾーンが必要です。"
            )

        if (
            end_at is not None
            and end_at.tzinfo is None
        ):
            raise ValueError(
                "終了日時にはタイムゾーンが必要です。"
            )

        if (
            start_at is not None
            and end_at is not None
            and start_at > end_at
        ):
            raise ValueError(
                "開始日時は終了日時以前にしてください。"
            )

        generated_at = self._current_time()

        if not self.database_path.exists():
            return StrategyPerformancePayload(
                generated_at=generated_at,
                period_start=start_at,
                period_end=end_at,
                rankings=(),
            )

        with sqlite3.connect(
            self.database_path
        ) as connection:
            if not self._table_exists(
                connection,
                "trade_journal",
            ):
                return StrategyPerformancePayload(
                    generated_at=generated_at,
                    period_start=start_at,
                    period_end=end_at,
                    rankings=(),
                )

            rows = self._load_rows(
                connection,
                start_at=start_at,
                end_at=end_at,
            )

        grouped: dict[
            str,
            list[dict[str, float]],
        ] = defaultdict(list)

        for row in rows:
            grouped[
                str(row["strategy_name"])
            ].append(row)

        rankings = tuple(
            sorted(
                (
                    self._analyze_strategy(
                        strategy_name,
                        values,
                    )
                    for strategy_name, values
                    in grouped.items()
                ),
                key=lambda item: (
                    -item.score,
                    -item.net_profit_loss,
                    item.strategy_name,
                ),
            )
        )

        return StrategyPerformancePayload(
            generated_at=generated_at,
            period_start=start_at,
            period_end=end_at,
            rankings=rankings,
        )

    def _load_rows(
        self,
        connection: sqlite3.Connection,
        *,
        start_at: datetime | None,
        end_at: datetime | None,
    ) -> tuple[dict[str, float], ...]:
        conditions: list[str] = []
        parameters: list[object] = []

        if start_at is not None:
            conditions.append("exit_at >= ?")
            parameters.append(
                start_at.astimezone(
                    timezone.utc
                ).isoformat()
            )

        if end_at is not None:
            conditions.append("exit_at <= ?")
            parameters.append(
                end_at.astimezone(
                    timezone.utc
                ).isoformat()
            )

        where_clause = (
            "WHERE " + " AND ".join(conditions)
            if conditions
            else ""
        )

        rows = connection.execute(
            f"""
            SELECT
                strategy_name,
                realized_profit_loss,
                return_rate,
                holding_minutes,
                maximum_favorable_excursion_rate,
                maximum_adverse_excursion_rate
            FROM trade_journal
            {where_clause}
            ORDER BY exit_at ASC, id ASC
            """,
            parameters,
        ).fetchall()

        return tuple(
            {
                "strategy_name": str(row[0]),
                "profit_loss": float(row[1]),
                "return_rate": float(row[2]),
                "holding_minutes": float(row[3]),
                "mfe_rate": (
                    float(row[4])
                    if row[4] is not None
                    else math.nan
                ),
                "mae_rate": (
                    float(row[5])
                    if row[5] is not None
                    else math.nan
                ),
            }
            for row in rows
        )

    def _analyze_strategy(
        self,
        strategy_name: str,
        values: list[dict[str, float]],
    ) -> StrategyPerformance:
        profit_losses = [
            value["profit_loss"]
            for value in values
        ]
        return_rates = [
            value["return_rate"]
            for value in values
        ]
        holding_minutes = [
            value["holding_minutes"]
            for value in values
        ]
        wins = [
            value
            for value in values
            if value["profit_loss"] > 0
        ]
        losses = [
            value
            for value in values
            if value["profit_loss"] < 0
        ]
        breakeven_count = (
            len(values)
            - len(wins)
            - len(losses)
        )

        gross_profit = sum(
            value["profit_loss"]
            for value in wins
        )
        gross_loss = sum(
            value["profit_loss"]
            for value in losses
        )
        net_profit_loss = sum(profit_losses)
        trade_count = len(values)
        win_rate = (
            len(wins) / trade_count
            if trade_count > 0
            else None
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
        maximum_drawdown = self._maximum_drawdown(
            profit_losses
        )
        cumulative_profit = 0.0
        peak_profit = 0.0
        maximum_drawdown_rate: float | None = None

        for profit_loss in profit_losses:
            cumulative_profit += profit_loss
            peak_profit = max(
                peak_profit,
                cumulative_profit,
            )

            if peak_profit > 0:
                drawdown_rate = (
                    cumulative_profit
                    - peak_profit
                ) / peak_profit
                maximum_drawdown_rate = min(
                    maximum_drawdown_rate or 0.0,
                    drawdown_rate,
                )

        average_mfe_rate = self._average_finite(
            value["mfe_rate"]
            for value in values
        )
        average_mae_rate = self._average_finite(
            value["mae_rate"]
            for value in values
        )
        average_win_rate = self._average(
            [
                value["return_rate"]
                for value in wins
            ]
        )
        average_loss_rate = self._average(
            [
                value["return_rate"]
                for value in losses
            ]
        )
        expectancy = self._average(
            profit_losses
        )

        return StrategyPerformance(
            strategy_name=self.DISPLAY_NAMES.get(
                strategy_name,
                strategy_name,
            ),
            trade_count=trade_count,
            win_count=len(wins),
            loss_count=len(losses),
            breakeven_count=breakeven_count,
            win_rate=win_rate,
            gross_profit=gross_profit,
            gross_loss=gross_loss,
            net_profit_loss=net_profit_loss,
            profit_factor=profit_factor,
            average_profit_loss=self._average(
                profit_losses
            ),
            average_win=self._average(
                [
                    value["profit_loss"]
                    for value in wins
                ]
            ),
            average_loss=self._average(
                [
                    value["profit_loss"]
                    for value in losses
                ]
            ),
            average_return_rate=self._average(
                return_rates
            ),
            average_win_rate=average_win_rate,
            average_loss_rate=average_loss_rate,
            expectancy=expectancy,
            average_holding_minutes=self._average(
                holding_minutes
            ),
            maximum_drawdown=maximum_drawdown,
            maximum_drawdown_rate=(
                maximum_drawdown_rate
            ),
            average_mfe_rate=average_mfe_rate,
            average_mae_rate=average_mae_rate,
            score=self._score(
                trade_count=trade_count,
                net_profit_loss=net_profit_loss,
                win_rate=win_rate,
                profit_factor=profit_factor,
                maximum_drawdown=maximum_drawdown,
            ),
        )

    @staticmethod
    def _maximum_drawdown(
        profit_losses: list[float],
    ) -> float:
        cumulative = 0.0
        peak = 0.0
        maximum_drawdown = 0.0

        for profit_loss in profit_losses:
            cumulative += profit_loss
            peak = max(
                peak,
                cumulative,
            )
            maximum_drawdown = min(
                maximum_drawdown,
                cumulative - peak,
            )

        return maximum_drawdown

    @staticmethod
    def _score(
        *,
        trade_count: int,
        net_profit_loss: float,
        win_rate: float | None,
        profit_factor: float | None,
        maximum_drawdown: float,
    ) -> float:
        if trade_count == 0:
            return 0.0

        sample_score = min(
            20.0,
            trade_count / 20.0 * 20.0,
        )
        win_score = min(
            20.0,
            max(
                0.0,
                (win_rate or 0.0) * 20.0,
            ),
        )
        profit_factor_score = (
            20.0
            if profit_factor is not None
            and math.isinf(profit_factor)
            else min(
                20.0,
                max(
                    0.0,
                    (profit_factor or 0.0)
                    / 2.0
                    * 20.0,
                ),
            )
        )
        profit_score = min(
            25.0,
            max(
                0.0,
                net_profit_loss / 100_000.0 * 25.0,
            ),
        )
        drawdown_penalty = min(
            15.0,
            abs(maximum_drawdown)
            / 100_000.0
            * 15.0,
        )

        return round(
            min(
                100.0,
                max(
                    0.0,
                    sample_score
                    + win_score
                    + profit_factor_score
                    + profit_score
                    - drawdown_penalty,
                ),
            ),
            4,
        )

    @staticmethod
    def _average(
        values: list[float],
    ) -> float | None:
        if not values:
            return None

        return sum(values) / len(values)

    @staticmethod
    def _average_finite(
        values,
    ) -> float | None:
        finite = [
            value
            for value in values
            if math.isfinite(value)
        ]

        if not finite:
            return None

        return sum(finite) / len(finite)

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

        return value.astimezone(timezone.utc)
