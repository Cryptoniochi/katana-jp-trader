"""Strategy Learning結果をSQLiteへ保存する。"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from app.learning.strategy_learning_models import (
    StrategyLearningRecord,
)


class StrategyLearningRepository:
    """学習結果の永続化を担当する。"""

    def __init__(
        self,
        database_path: Path,
    ) -> None:
        self.database_path = Path(database_path)

    def initialize(self) -> None:
        self.database_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        with sqlite3.connect(
            self.database_path
        ) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS
                strategy_learning_summary (
                    code TEXT NOT NULL,
                    strategy_name TEXT NOT NULL,
                    trade_count INTEGER NOT NULL,
                    win_count INTEGER NOT NULL,
                    loss_count INTEGER NOT NULL,
                    breakeven_count INTEGER NOT NULL,
                    win_rate REAL,
                    gross_profit REAL NOT NULL,
                    gross_loss REAL NOT NULL,
                    net_profit_loss REAL NOT NULL,
                    profit_factor REAL,
                    expectancy REAL,
                    average_return_rate REAL,
                    average_holding_minutes REAL,
                    sample_confidence REAL NOT NULL,
                    historical_score REAL NOT NULL,
                    eligible_for_feedback INTEGER NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (
                        code,
                        strategy_name
                    )
                )
                """
            )
            connection.commit()

    def replace_all(
        self,
        records: tuple[
            StrategyLearningRecord,
            ...,
        ],
    ) -> None:
        self.initialize()

        with sqlite3.connect(
            self.database_path
        ) as connection:
            connection.execute(
                "DELETE FROM strategy_learning_summary"
            )
            connection.executemany(
                """
                INSERT INTO strategy_learning_summary (
                    code,
                    strategy_name,
                    trade_count,
                    win_count,
                    loss_count,
                    breakeven_count,
                    win_rate,
                    gross_profit,
                    gross_loss,
                    net_profit_loss,
                    profit_factor,
                    expectancy,
                    average_return_rate,
                    average_holding_minutes,
                    sample_confidence,
                    historical_score,
                    eligible_for_feedback,
                    updated_at
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                [
                    (
                        item.code,
                        item.strategy_name,
                        item.trade_count,
                        item.win_count,
                        item.loss_count,
                        item.breakeven_count,
                        item.win_rate,
                        item.gross_profit,
                        item.gross_loss,
                        item.net_profit_loss,
                        item.profit_factor,
                        item.expectancy,
                        item.average_return_rate,
                        item.average_holding_minutes,
                        item.sample_confidence,
                        item.historical_score,
                        int(item.eligible_for_feedback),
                        item.updated_at.isoformat(),
                    )
                    for item in records
                ],
            )
            connection.commit()

    def load_for_code(
        self,
        code: str,
    ) -> tuple[StrategyLearningRecord, ...]:
        self.initialize()

        with sqlite3.connect(
            self.database_path
        ) as connection:
            rows = connection.execute(
                """
                SELECT
                    code,
                    strategy_name,
                    trade_count,
                    win_count,
                    loss_count,
                    breakeven_count,
                    win_rate,
                    gross_profit,
                    gross_loss,
                    net_profit_loss,
                    profit_factor,
                    expectancy,
                    average_return_rate,
                    average_holding_minutes,
                    sample_confidence,
                    historical_score,
                    eligible_for_feedback,
                    updated_at
                FROM strategy_learning_summary
                WHERE code = ?
                ORDER BY historical_score DESC,
                         trade_count DESC,
                         strategy_name ASC
                """,
                (code.strip(),),
            ).fetchall()

        from datetime import datetime

        return tuple(
            StrategyLearningRecord(
                code=str(row[0]),
                strategy_name=str(row[1]),
                trade_count=int(row[2]),
                win_count=int(row[3]),
                loss_count=int(row[4]),
                breakeven_count=int(row[5]),
                win_rate=(
                    None
                    if row[6] is None
                    else float(row[6])
                ),
                gross_profit=float(row[7]),
                gross_loss=float(row[8]),
                net_profit_loss=float(row[9]),
                profit_factor=(
                    None
                    if row[10] is None
                    else float(row[10])
                ),
                expectancy=(
                    None
                    if row[11] is None
                    else float(row[11])
                ),
                average_return_rate=(
                    None
                    if row[12] is None
                    else float(row[12])
                ),
                average_holding_minutes=(
                    None
                    if row[13] is None
                    else float(row[13])
                ),
                sample_confidence=float(row[14]),
                historical_score=float(row[15]),
                eligible_for_feedback=bool(row[16]),
                updated_at=datetime.fromisoformat(
                    str(row[17])
                ),
            )
            for row in rows
        )
