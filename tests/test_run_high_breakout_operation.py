"""High Breakout運用Orchestratorのテスト。"""

import sqlite3
from pathlib import Path

import pytest

import app.run_high_breakout_operation as module


def create_database(
    tmp_path: Path,
) -> Path:
    database_path = tmp_path / "katana.db"

    with sqlite3.connect(
        database_path
    ) as connection:
        connection.execute(
            """
            CREATE TABLE market_bars (
                interval_minutes INTEGER NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE high_breakout_candidates (
                id INTEGER PRIMARY KEY
            )
            """
        )
        connection.executemany(
            """
            INSERT INTO market_bars (
                interval_minutes
            )
            VALUES (?)
            """,
            [
                (1440,),
                (1440,),
                (5,),
            ],
        )
        connection.execute(
            """
            INSERT INTO high_breakout_candidates (
                id
            )
            VALUES (1)
            """
        )
        connection.commit()

    return database_path


def test_result_successful_property() -> None:
    result = module.HighBreakoutOperationResult(
        daily_bar_exit_code=0,
        screening_exit_code=0,
        daily_bar_count=10,
        candidate_count=2,
        paper_trading_started=False,
    )

    assert result.successful


def test_count_rows_returns_matching_count(
    tmp_path: Path,
) -> None:
    database_path = create_database(
        tmp_path
    )

    assert module._count_rows(
        database_path,
        """
        SELECT COUNT(*)
        FROM market_bars
        WHERE interval_minutes = ?
        """,
        (1440,),
    ) == 2


def test_execute_operation_runs_both_steps(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = create_database(
        tmp_path
    )
    calls: list[
        tuple[str, list[str]]
    ] = []

    def fake_build(arguments):
        calls.append(
            (
                "build",
                list(arguments),
            )
        )
        return 0

    def fake_screen(arguments):
        calls.append(
            (
                "screen",
                list(arguments),
            )
        )
        return 0

    monkeypatch.setattr(
        module,
        "run_build_daily_bars",
        fake_build,
    )
    monkeypatch.setattr(
        module,
        "run_high_breakout_screening",
        fake_screen,
    )

    result = module.execute_operation(
        database_path=database_path,
        watchlist_path=tmp_path / "watchlist.txt",
        output_directory=tmp_path / "reports",
        source_interval_minutes=5,
        codes=("7203",),
        minimum_volume_ratio=1.5,
        minimum_turnover=100_000_000.0,
        start_paper_trading=False,
        paper_trading_dry_run=False,
    )

    assert [
        name
        for name, _arguments in calls
    ] == [
        "build",
        "screen",
    ]
    assert result.daily_bar_count == 2
    assert result.candidate_count == 1
    assert not result.paper_trading_started


def test_operation_rejects_invalid_interval(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        ValueError,
        match="時間足",
    ):
        module.execute_operation(
            database_path=tmp_path / "katana.db",
            watchlist_path=tmp_path / "watchlist.txt",
            output_directory=tmp_path / "reports",
            source_interval_minutes=0,
            codes=("7203",),
            minimum_volume_ratio=1.5,
            minimum_turnover=0.0,
            start_paper_trading=False,
            paper_trading_dry_run=False,
        )
