"""Watchlist-to-Execution Integrity Audit tests."""

import json
import sqlite3
from datetime import date
from pathlib import Path

from app.runtime.watchlist_execution_integrity_service import (
    WatchlistExecutionIntegrityService,
)


DAY = date(2026, 8, 12)


def _write_explainability(path: Path) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    path.write_text(
        json.dumps(
            {
                "target_date": "2026-08-12",
                "candidates": [
                    {
                        "code": "8306",
                        "selected": True,
                    },
                    {
                        "code": "6758",
                        "selected": True,
                    },
                    {
                        "code": "9432",
                        "selected": True,
                    },
                    {
                        "code": "7203",
                        "selected": False,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )


def _write_trace(path: Path) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    events = [
        {
            "occurred_at": "2026-08-12T00:00:01+00:00",
            "event_type": "runtime_started",
            "signal_id": None,
            "code": None,
            "payload": {
                "codes": [
                    "8306",
                    "6758",
                    "9432",
                ]
            },
        },
        {
            "occurred_at": "2026-08-12T01:00:00+00:00",
            "event_type": "signal_generated",
            "signal_id": "s1",
            "code": "6758",
            "payload": {},
        },
        {
            "occurred_at": "2026-08-12T01:00:01+00:00",
            "event_type": "broker_executed",
            "signal_id": "s1",
            "code": "6758",
            "payload": {},
        },
    ]
    path.write_text(
        "\n".join(
            json.dumps(event)
            for event in events
        )
        + "\n",
        encoding="utf-8",
    )


def _create_database(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE trade_signals (
                signal_id TEXT PRIMARY KEY,
                code TEXT NOT NULL,
                generated_at TEXT NOT NULL
            );
            CREATE TABLE trade_executions (
                execution_id TEXT PRIMARY KEY,
                code TEXT NOT NULL,
                executed_at TEXT NOT NULL
            );
            """
        )
        connection.execute(
            """
            INSERT INTO trade_signals
            VALUES (
                's1',
                '6758',
                '2026-08-12T01:00:00+00:00'
            )
            """
        )
        connection.execute(
            """
            INSERT INTO trade_executions
            VALUES (
                'e1',
                '6758',
                '2026-08-12T01:00:01+00:00'
            )
            """
        )
        connection.commit()


def test_integrity_passes_for_matching_pipeline(
    tmp_path: Path,
) -> None:
    database = tmp_path / "katana.db"
    watchlist = tmp_path / "watchlist.txt"
    explainability = tmp_path / "latest.json"
    trace = tmp_path / "trace.jsonl"

    _create_database(database)
    _write_explainability(explainability)
    _write_trace(trace)
    watchlist.write_text(
        "8306\n6758\n9432\n",
        encoding="utf-8",
    )

    result = WatchlistExecutionIntegrityService(
        database_path=database,
        watchlist_path=watchlist,
        explainability_path=explainability,
        trace_path=trace,
    ).audit(
        trading_date=DAY
    )

    assert result.integrity_ok is True
    assert result.selected_count == 3
    assert result.loaded_count == 3
    assert result.monitored_count == 3
    assert result.signal_count == 1
    assert result.execution_count == 1
    assert result.orphan_signal_codes == ()
    assert result.orphan_execution_codes == ()


def test_integrity_fails_when_selected_code_not_loaded(
    tmp_path: Path,
) -> None:
    database = tmp_path / "katana.db"
    watchlist = tmp_path / "watchlist.txt"
    explainability = tmp_path / "latest.json"
    trace = tmp_path / "trace.jsonl"

    _create_database(database)
    _write_explainability(explainability)
    _write_trace(trace)
    watchlist.write_text(
        "8306\n6758\n",
        encoding="utf-8",
    )

    result = WatchlistExecutionIntegrityService(
        database_path=database,
        watchlist_path=watchlist,
        explainability_path=explainability,
        trace_path=trace,
    ).audit(
        trading_date=DAY
    )

    assert result.integrity_ok is False
    assert result.selected_not_loaded_codes == (
        "9432",
    )


def test_latest_runtime_session_replaces_stale_monitored_codes(
    tmp_path: Path,
) -> None:
    database = tmp_path / "katana.db"
    watchlist = tmp_path / "watchlist.txt"
    explainability = tmp_path / "latest.json"
    trace = tmp_path / "trace.jsonl"

    _create_database(database)
    _write_explainability(explainability)
    watchlist.write_text(
        "8306\n6758\n9432\n",
        encoding="utf-8",
    )

    events = [
        {
            "occurred_at": "2026-08-12T00:00:01+00:00",
            "event_type": "runtime_started",
            "signal_id": None,
            "code": None,
            "payload": {
                "codes": [
                    "8306",
                    "7203",
                    "6758",
                    "9432",
                    "9984",
                ]
            },
        },
        {
            "occurred_at": "2026-08-12T00:10:00+00:00",
            "event_type": "runtime_stopped",
            "signal_id": None,
            "code": None,
            "payload": {"reason": "restart"},
        },
        {
            "occurred_at": "2026-08-12T00:20:00+00:00",
            "event_type": "runtime_started",
            "signal_id": None,
            "code": None,
            "payload": {
                "codes": [
                    "8306",
                    "6758",
                    "9432",
                ]
            },
        },
    ]
    trace.write_text(
        "\n".join(json.dumps(event) for event in events)
        + "\n",
        encoding="utf-8",
    )

    result = WatchlistExecutionIntegrityService(
        database_path=database,
        watchlist_path=watchlist,
        explainability_path=explainability,
        trace_path=trace,
    ).audit(
        trading_date=DAY
    )

    assert result.integrity_ok is True
    assert result.monitored_codes == (
        "6758",
        "8306",
        "9432",
    )
    assert result.monitored_not_loaded_codes == ()


def test_integrity_fails_for_monitored_code_not_in_watchlist(
    tmp_path: Path,
) -> None:
    database = tmp_path / "katana.db"
    watchlist = tmp_path / "watchlist.txt"
    explainability = tmp_path / "latest.json"
    trace = tmp_path / "trace.jsonl"

    _create_database(database)
    _write_explainability(explainability)
    watchlist.write_text(
        "8306\n6758\n9432\n",
        encoding="utf-8",
    )

    events = [
        {
            "occurred_at": "2026-08-12T00:00:01+00:00",
            "event_type": "runtime_started",
            "signal_id": None,
            "code": None,
            "payload": {
                "codes": [
                    "8306",
                    "7203",
                    "6758",
                    "9432",
                ]
            },
        },
    ]
    trace.write_text(
        "\n".join(json.dumps(event) for event in events)
        + "\n",
        encoding="utf-8",
    )

    result = WatchlistExecutionIntegrityService(
        database_path=database,
        watchlist_path=watchlist,
        explainability_path=explainability,
        trace_path=trace,
    ).audit(
        trading_date=DAY
    )

    assert result.integrity_ok is False
    assert result.monitored_not_loaded_codes == (
        "7203",
    )
