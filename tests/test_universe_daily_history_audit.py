"""Universe Daily History Auditのテスト。"""

import json
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path

from app.runtime.universe_daily_history_audit_service import (
    UniverseDailyHistoryAuditService,
)


NOW = datetime(
    2026,
    8,
    10,
    tzinfo=timezone.utc,
)
DAY = date(2026, 8, 7)


def _create_database(
    path: Path,
) -> None:
    with sqlite3.connect(
        path
    ) as connection:
        connection.executescript(
            """
            CREATE TABLE listed_symbols (
                code TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                market TEXT NOT NULL,
                security_type TEXT NOT NULL,
                is_active INTEGER NOT NULL
            );

            CREATE TABLE market_bars (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL,
                traded_at TEXT NOT NULL,
                interval_minutes INTEGER NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                volume INTEGER NOT NULL,
                data_source TEXT NOT NULL
            );
            """
        )

        for code in (
            "1001",
            "1002",
            "1003",
            "1004",
        ):
            connection.execute(
                """
                INSERT INTO listed_symbols (
                    code,
                    name,
                    market,
                    security_type,
                    is_active
                )
                VALUES (
                    ?,
                    ?,
                    'Prime',
                    'common_stock',
                    1
                )
                """,
                (
                    code,
                    f"Name {code}",
                ),
            )

        # 1001/1002/1003は対象日取得済み。
        for code in (
            "1001",
            "1002",
            "1003",
        ):
            connection.execute(
                """
                INSERT INTO market_bars (
                    code,
                    traded_at,
                    interval_minutes,
                    open,
                    high,
                    low,
                    close,
                    volume,
                    data_source
                )
                VALUES (
                    ?,
                    '2026-08-07T00:00:00+00:00',
                    1440,
                    100,
                    110,
                    90,
                    105,
                    1000,
                    'test'
                )
                """,
                (
                    code,
                ),
            )

        # 1001だけ過去分を追加し5日履歴へ。
        for day in (
            1,
            2,
            3,
            4,
        ):
            connection.execute(
                """
                INSERT INTO market_bars (
                    code,
                    traded_at,
                    interval_minutes,
                    open,
                    high,
                    low,
                    close,
                    volume,
                    data_source
                )
                VALUES (
                    '1001',
                    ?,
                    1440,
                    100,
                    110,
                    90,
                    105,
                    1000,
                    'test'
                )
                """,
                (
                    f"2026-08-0{day}"
                    "T00:00:00+00:00",
                ),
            )

        connection.commit()


def test_terminal_skip_completes_daily_audit(
    tmp_path: Path,
) -> None:
    database = tmp_path / "katana.db"
    terminal = tmp_path / "unavailable.json"
    _create_database(database)

    terminal.write_text(
        json.dumps(
            {
                "trading_date": "2026-08-07",
                "entries": {
                    "1004": {
                        "reason": "no board values"
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    result = UniverseDailyHistoryAuditService(
        database_path=database,
        minimum_effective_coverage_ratio=0.99,
        terminal_skip_path=terminal,
        now_provider=lambda: NOW,
    ).audit(
        trading_date=DAY
    )

    assert result.active_universe_count == 4
    assert result.collected_count == 3
    assert result.missing_count == 1
    assert result.terminal_skipped_count == 1
    assert result.unexplained_missing_count == 0
    assert result.effective_coverage_ratio == 1.0
    assert result.completed is True
    assert result.symbols_with_5_days == 1


def test_unexplained_missing_fails_audit(
    tmp_path: Path,
) -> None:
    database = tmp_path / "katana.db"
    _create_database(database)

    result = UniverseDailyHistoryAuditService(
        database_path=database,
        minimum_effective_coverage_ratio=0.75,
        terminal_skip_path=(
            tmp_path / "missing.json"
        ),
        now_provider=lambda: NOW,
    ).audit(
        trading_date=DAY
    )

    assert result.collection_ratio == 0.75
    assert result.unexplained_missing_count == 1
    assert result.unexplained_missing_codes == (
        "1004",
    )
    assert result.completed is False
