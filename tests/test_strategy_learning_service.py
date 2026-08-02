"""StrategyLearningServiceのテスト。"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from app.learning.strategy_learning_service import (
    StrategyLearningService,
)


NOW = datetime(
    2026,
    8,
    3,
    tzinfo=timezone.utc,
)


def create_trade_journal(
    database: Path,
) -> None:
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            CREATE TABLE trade_journal (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL,
                strategy_name TEXT NOT NULL,
                entry_at TEXT NOT NULL,
                exit_at TEXT NOT NULL,
                realized_profit_loss REAL NOT NULL,
                return_rate REAL NOT NULL,
                holding_minutes REAL NOT NULL
            )
            """
        )

        rows = []

        for index in range(12):
            rows.append(
                (
                    "7203",
                    "pullback-breakout-v1",
                    NOW.isoformat(),
                    NOW.isoformat(),
                    5000.0 if index < 8 else -2000.0,
                    0.02 if index < 8 else -0.01,
                    30.0,
                )
            )

        for index in range(12):
            rows.append(
                (
                    "7203",
                    "opening-range-breakout-v2",
                    NOW.isoformat(),
                    NOW.isoformat(),
                    1000.0 if index < 4 else -2500.0,
                    0.005 if index < 4 else -0.012,
                    20.0,
                )
            )

        connection.executemany(
            """
            INSERT INTO trade_journal (
                code,
                strategy_name,
                entry_at,
                exit_at,
                realized_profit_loss,
                return_rate,
                holding_minutes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        connection.commit()


def test_learning_recommends_best_eligible_strategy(
    tmp_path: Path,
) -> None:
    database = tmp_path / "katana.db"
    create_trade_journal(database)

    report = StrategyLearningService(
        database,
        minimum_trade_count=10,
        full_confidence_trade_count=30,
        now_provider=lambda: NOW,
    ).analyze_and_persist()

    recommendation = report.recommendations[0]

    assert recommendation.code == "7203"
    assert recommendation.preferred_strategy == (
        "pullback-breakout-v1"
    )
    assert recommendation.eligible_strategy_count == 2


def test_learning_waits_for_minimum_sample(
    tmp_path: Path,
) -> None:
    database = tmp_path / "katana.db"

    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            CREATE TABLE trade_journal (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL,
                strategy_name TEXT NOT NULL,
                entry_at TEXT NOT NULL,
                exit_at TEXT NOT NULL,
                realized_profit_loss REAL NOT NULL,
                return_rate REAL NOT NULL,
                holding_minutes REAL NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO trade_journal (
                code,
                strategy_name,
                entry_at,
                exit_at,
                realized_profit_loss,
                return_rate,
                holding_minutes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "9984",
                "opening-range-breakout-v2",
                NOW.isoformat(),
                NOW.isoformat(),
                10000.0,
                0.03,
                15.0,
            ),
        )
        connection.commit()

    report = StrategyLearningService(
        database,
        minimum_trade_count=10,
        now_provider=lambda: NOW,
    ).analyze_and_persist()

    recommendation = report.recommendations[0]

    assert recommendation.preferred_strategy is None
    assert recommendation.eligible_strategy_count == 0
    assert report.records[0].historical_score < 20.0


def test_learning_creates_summary_table(
    tmp_path: Path,
) -> None:
    database = tmp_path / "katana.db"
    create_trade_journal(database)

    StrategyLearningService(
        database,
        now_provider=lambda: NOW,
    ).analyze_and_persist()

    with sqlite3.connect(database) as connection:
        count = connection.execute(
            """
            SELECT COUNT(*)
            FROM strategy_learning_summary
            """
        ).fetchone()[0]

    assert count == 2
