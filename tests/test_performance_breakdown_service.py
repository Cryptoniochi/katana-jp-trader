"""PerformanceBreakdownAnalyzerのテスト。"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.analytics.performance_breakdown_service import (
    PerformanceBreakdownAnalyzer,
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
                code TEXT,
                entry_at TEXT,
                exit_at TEXT,
                exit_reason TEXT,
                realized_profit_loss REAL,
                return_rate REAL
            )
            """
        )
        connection.executemany(
            """
            INSERT INTO trade_journal (
                code,
                entry_at,
                exit_at,
                exit_reason,
                realized_profit_loss,
                return_rate
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "7203",
                    "2026-08-03T00:30:00+00:00",
                    "2026-08-03T01:00:00+00:00",
                    "take_profit",
                    2000.0,
                    0.02,
                ),
                (
                    "7203",
                    "2026-08-03T01:30:00+00:00",
                    "2026-08-03T02:00:00+00:00",
                    "stop_loss",
                    -1000.0,
                    -0.01,
                ),
                (
                    "6758",
                    "2026-08-04T00:30:00+00:00",
                    "2026-08-04T01:00:00+00:00",
                    "take_profit",
                    500.0,
                    0.005,
                ),
            ],
        )
        connection.commit()

    return path


def test_analyzer_builds_all_breakdowns(
    tmp_path: Path,
) -> None:
    payload = PerformanceBreakdownAnalyzer(
        create_database(tmp_path),
        now_provider=lambda: NOW,
    ).analyze()

    assert len(payload.weekday) == 2
    assert len(payload.entry_hour) == 2
    assert len(payload.symbol) == 2
    assert len(payload.exit_reason) == 2

    symbol_rows = {
        item.key: item
        for item in payload.symbol
    }
    assert symbol_rows["7203"].trade_count == 2
    assert symbol_rows["7203"].net_profit_loss == pytest.approx(
        1000.0
    )
    assert symbol_rows["7203"].profit_factor == pytest.approx(
        2.0
    )


def test_analyzer_returns_empty_without_database(
    tmp_path: Path,
) -> None:
    payload = PerformanceBreakdownAnalyzer(
        tmp_path / "missing.db",
        now_provider=lambda: NOW,
    ).analyze()

    assert payload.weekday == ()
    assert payload.symbol == ()
