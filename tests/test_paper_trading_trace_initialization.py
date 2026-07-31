"""Trace初期化と起動イベントのテスト。"""

import json
from pathlib import Path

from app.risk.paper_trading_trace import (
    PaperTradingTraceRecorder,
)


def test_recorder_creates_file_immediately(
    tmp_path: Path,
) -> None:
    path = tmp_path / "logs" / "risk" / "trace.jsonl"

    PaperTradingTraceRecorder(output_path=path)

    assert path.exists()
    assert path.read_text(encoding="utf-8") == ""


def test_runtime_started_writes_marker(
    tmp_path: Path,
) -> None:
    path = tmp_path / "logs" / "risk" / "trace.jsonl"
    recorder = PaperTradingTraceRecorder(
        output_path=path
    )

    recorder.runtime_started(
        market_data_mode="kabu-station-realtime",
        codes=("7203", "9984"),
        database_path=tmp_path / "katana.db",
    )

    rows = [
        json.loads(line)
        for line in path.read_text(
            encoding="utf-8"
        ).splitlines()
    ]

    assert len(rows) == 1
    assert rows[0]["event_type"] == "runtime_started"
    assert rows[0]["signal_id"] is None
    assert rows[0]["code"] is None
    assert rows[0]["payload"]["code_count"] == 2
    assert rows[0]["payload"]["market_data_mode"] == (
        "kabu-station-realtime"
    )
