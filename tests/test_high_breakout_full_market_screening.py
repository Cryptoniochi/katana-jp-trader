"""High Breakout?????????????????"""

from pathlib import Path
import sqlite3

from app.database import initialize_database
import app.run_high_breakout_operation as operation


def _insert_bar(
    database_path: Path,
    *,
    code: str,
    interval_minutes: int,
) -> None:
    with sqlite3.connect(database_path) as connection:
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
                data_source,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                code,
                "2026-10-23T00:00:00+00:00",
                interval_minutes,
                1000.0,
                1010.0,
                990.0,
                1005.0,
                100000,
                "test",
                "2026-10-23T06:40:00+00:00",
                "2026-10-23T06:40:00+00:00",
            ),
        )
        connection.commit()


def test_load_daily_market_codes_uses_full_database_universe(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "katana.db"
    initialize_database(database_path)

    _insert_bar(
        database_path,
        code="7203",
        interval_minutes=1440,
    )
    _insert_bar(
        database_path,
        code="7354",
        interval_minutes=1440,
    )
    _insert_bar(
        database_path,
        code="277A",
        interval_minutes=1440,
    )
    _insert_bar(
        database_path,
        code="9999",
        interval_minutes=5,
    )

    assert operation._load_daily_market_codes(
        database_path
    ) == (
        "277A",
        "7203",
        "7354",
    )


def test_operation_keeps_daily_build_codes_but_screens_full_market(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "katana.db"
    initialize_database(database_path)

    _insert_bar(
        database_path,
        code="7203",
        interval_minutes=1440,
    )
    _insert_bar(
        database_path,
        code="7354",
        interval_minutes=1440,
    )
    _insert_bar(
        database_path,
        code="277A",
        interval_minutes=1440,
    )

    build_calls = []
    screening_calls = []

    monkeypatch.setattr(
        operation,
        "run_build_daily_bars",
        lambda arguments: build_calls.append(tuple(arguments)) or 0,
    )
    monkeypatch.setattr(
        operation,
        "run_high_breakout_screening",
        lambda arguments: screening_calls.append(tuple(arguments)) or 0,
    )

    result = operation.execute_operation(
        database_path=database_path,
        watchlist_path=tmp_path / "watchlist.txt",
        output_directory=tmp_path / "reports",
        source_interval_minutes=5,
        codes=("7203",),
        minimum_volume_ratio=1.5,
        minimum_turnover=100_000_000.0,
        target_trading_date=None,
        start_paper_trading=False,
        paper_trading_dry_run=False,
    )

    assert result.successful
    assert len(build_calls) == 1
    assert len(screening_calls) == 1

    build_arguments = build_calls[0]
    screening_arguments = screening_calls[0]

    assert build_arguments.count("--code") == 1
    assert "7203" in build_arguments
    assert "7354" not in build_arguments
    assert "277A" not in build_arguments

    assert screening_arguments.count("--code") == 3
    assert "7203" in screening_arguments
    assert "7354" in screening_arguments
    assert "277A" in screening_arguments


def test_operation_preserves_high_breakout_thresholds(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "katana.db"
    initialize_database(database_path)

    _insert_bar(
        database_path,
        code="7354",
        interval_minutes=1440,
    )

    screening_calls = []

    monkeypatch.setattr(
        operation,
        "run_build_daily_bars",
        lambda _arguments: 0,
    )
    monkeypatch.setattr(
        operation,
        "run_high_breakout_screening",
        lambda arguments: screening_calls.append(tuple(arguments)) or 0,
    )

    operation.execute_operation(
        database_path=database_path,
        watchlist_path=tmp_path / "watchlist.txt",
        output_directory=tmp_path / "reports",
        source_interval_minutes=5,
        codes=("7203",),
        minimum_volume_ratio=1.5,
        minimum_turnover=100_000_000.0,
        target_trading_date=None,
        start_paper_trading=False,
        paper_trading_dry_run=False,
    )

    arguments = screening_calls[0]

    volume_index = arguments.index("--minimum-volume-ratio")
    turnover_index = arguments.index("--minimum-turnover")

    assert arguments[volume_index + 1] == "1.5"
    assert arguments[turnover_index + 1] == "100000000.0"
