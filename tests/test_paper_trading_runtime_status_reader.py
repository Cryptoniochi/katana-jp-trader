"""PaperTradingRuntimeStatusReaderのテスト。"""

import json

from app.dashboard.paper_trading_runtime_status_reader import (
    PaperTradingRuntimeStatusReader,
)


def test_missing_runtime_status_returns_empty_payload(
    tmp_path,
) -> None:
    reader = PaperTradingRuntimeStatusReader(
        tmp_path / "missing.json"
    )

    payload = reader.read()

    assert payload["available"] is False
    assert payload["state"] == "not_reported"
    assert payload["cycle_count"] == 0


def test_reader_returns_runtime_payload(
    tmp_path,
) -> None:
    path = tmp_path / "runtime.json"
    path.write_text(
        json.dumps(
            {
                "state": "running",
                "cycle_count": 12,
                "signal_count": 2,
            }
        ),
        encoding="utf-8",
    )

    payload = PaperTradingRuntimeStatusReader(
        path
    ).read()

    assert payload["available"] is True
    assert payload["state"] == "running"
    assert payload["cycle_count"] == 12
    assert payload["signal_count"] == 2
