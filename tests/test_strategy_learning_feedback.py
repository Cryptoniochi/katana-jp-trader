"""StrategyLearningFeedbackProviderのテスト。"""

import sqlite3
from pathlib import Path

from app.learning.strategy_learning_feedback import (
    StrategyLearningFeedbackProvider,
)


def test_provider_maps_versioned_strategy_names(
    tmp_path: Path,
) -> None:
    database = tmp_path / "katana.db"

    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            CREATE TABLE strategy_learning_summary (
                code TEXT NOT NULL,
                strategy_name TEXT NOT NULL,
                trade_count INTEGER NOT NULL,
                historical_score REAL NOT NULL,
                sample_confidence REAL NOT NULL,
                eligible_for_feedback INTEGER NOT NULL
            )
            """
        )
        connection.executemany(
            """
            INSERT INTO strategy_learning_summary
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "7203",
                    "pullback-breakout-v1",
                    12,
                    8.5,
                    0.4,
                    1,
                ),
                (
                    "7203",
                    "opening-range-breakout-v2",
                    4,
                    19.0,
                    0.1,
                    0,
                ),
            ],
        )

    feedback = StrategyLearningFeedbackProvider(
        database
    ).for_code("7203")

    assert feedback is not None
    assert len(feedback.strategies) == 1
    assert feedback.strategies[0].strategy_name == (
        "pullback"
    )
    assert feedback.best.historical_score == 8.5
