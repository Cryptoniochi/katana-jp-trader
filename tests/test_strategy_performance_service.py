"""StrategyPerformanceAnalyzerのテスト。"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.analytics.strategy_performance_service import (
    StrategyPerformanceAnalyzer,
)


NOW = datetime(
    2026,
    8,
    3,
    12,
    0,
    tzinfo=timezone.utc,
)


def create_database(
    tmp_path: Path,
) -> Path:
    path = tmp_path / "katana.db"

    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE trade_journal (
                id INTEGER PRIMARY KEY,
                strategy_name TEXT,
                exit_at TEXT,
                realized_profit_loss REAL,
                return_rate REAL,
                holding_minutes REAL,
                maximum_favorable_excursion_rate REAL,
                maximum_adverse_excursion_rate REAL
            )
            """
        )
        connection.executemany(
            """
            INSERT INTO trade_journal (
                strategy_name,
                exit_at,
                realized_profit_loss,
                return_rate,
                holding_minutes,
                maximum_favorable_excursion_rate,
                maximum_adverse_excursion_rate
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "opening-range-breakout-v2",
                    "2026-08-01T01:00:00+00:00",
                    2000.0,
                    0.02,
                    30.0,
                    0.03,
                    -0.005,
                ),
                (
                    "opening-range-breakout-v2",
                    "2026-08-02T01:00:00+00:00",
                    -1000.0,
                    -0.01,
                    45.0,
                    0.01,
                    -0.02,
                ),
                (
                    "pullback-breakout-v1",
                    "2026-08-02T02:00:00+00:00",
                    500.0,
                    0.005,
                    60.0,
                    0.01,
                    -0.002,
                ),
            ],
        )
        connection.commit()

    return path


def test_analyzer_builds_rankings(
    tmp_path: Path,
) -> None:
    payload = StrategyPerformanceAnalyzer(
        create_database(tmp_path),
        now_provider=lambda: NOW,
    ).analyze()

    assert len(payload.rankings) == 2
    rows = {
        item.strategy_name: item
        for item in payload.rankings
    }

    orb = rows["ORB"]
    assert orb.trade_count == 2
    assert orb.win_count == 1
    assert orb.loss_count == 1
    assert orb.win_rate == pytest.approx(0.5)
    assert orb.gross_profit == pytest.approx(2000.0)
    assert orb.gross_loss == pytest.approx(-1000.0)
    assert orb.net_profit_loss == pytest.approx(1000.0)
    assert orb.profit_factor == pytest.approx(2.0)
    assert orb.average_holding_minutes == pytest.approx(37.5)
    assert orb.maximum_drawdown == pytest.approx(-1000.0)


def test_analyzer_returns_empty_without_database(
    tmp_path: Path,
) -> None:
    payload = StrategyPerformanceAnalyzer(
        tmp_path / "missing.db",
        now_provider=lambda: NOW,
    ).analyze()

    assert payload.rankings == ()
