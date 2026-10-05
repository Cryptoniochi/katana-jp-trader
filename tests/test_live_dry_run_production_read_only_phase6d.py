from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.live.live_dry_run_production_read_only import (
    ProductionReadOnlyPaths,
    SavedPaperRuntimeStatusProvider,
)


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_saved_runtime_status_accepts_fresh_running_state(tmp_path: Path):
    now = datetime(2026, 10, 5, 5, 0, tzinfo=timezone.utc)
    path = tmp_path / "runtime.json"
    _write(path, {
        "available": True,
        "generated_at": (now - timedelta(seconds=10)).isoformat(),
        "state": "running",
        "error_message": None,
    })
    provider = SavedPaperRuntimeStatusProvider(
        path, stale_after_seconds=180, now_provider=lambda: now
    )
    assert provider.runtime_health_ok() is True
    assert provider.heartbeat_alive() is True


def test_saved_runtime_status_fails_closed_when_missing(tmp_path: Path):
    provider = SavedPaperRuntimeStatusProvider(
        tmp_path / "missing.json",
        now_provider=lambda: datetime(2026, 10, 5, tzinfo=timezone.utc),
    )
    assert provider.runtime_health_ok() is False
    assert provider.heartbeat_alive() is False


def test_saved_runtime_status_fails_closed_when_stale(tmp_path: Path):
    now = datetime(2026, 10, 5, 5, 0, tzinfo=timezone.utc)
    path = tmp_path / "runtime.json"
    _write(path, {
        "available": True,
        "generated_at": (now - timedelta(seconds=181)).isoformat(),
        "state": "running",
        "error_message": None,
    })
    provider = SavedPaperRuntimeStatusProvider(
        path, stale_after_seconds=180, now_provider=lambda: now
    )
    assert provider.runtime_health_ok() is False
    assert provider.heartbeat_alive() is False


def test_saved_runtime_status_fails_closed_on_error_message(tmp_path: Path):
    now = datetime(2026, 10, 5, 5, 0, tzinfo=timezone.utc)
    path = tmp_path / "runtime.json"
    _write(path, {
        "available": True,
        "generated_at": now.isoformat(),
        "state": "running",
        "error_message": "cycle failed",
    })
    provider = SavedPaperRuntimeStatusProvider(
        path, now_provider=lambda: now
    )
    assert provider.runtime_health_ok() is False
    assert provider.heartbeat_alive() is True


def test_default_paths_are_read_only_production_sources():
    paths = ProductionReadOnlyPaths()
    assert paths.paper_database_path == Path("data/katana.db")
    assert paths.runtime_status_path == Path(
        "reports/service/paper_trading_runtime_status.json"
    )
    assert paths.kabu_station_report_path == Path(
        "reports/live/kabu_station_read_only.json"
    )
    assert paths.three_way_reconciliation_report_path == Path(
        "reports/live/three_way_reconciliation.json"
    )
    assert paths.fault_tolerance_state_path == Path(
        "reports/live/fault_tolerance_state.json"
    )
    assert paths.manual_kill_switch_state_path == Path(
        "reports/live/manual_kill_switch_state.json"
    )


def test_production_read_only_module_has_no_network_or_real_submit_primitives():
    source = Path("app/live/live_dry_run_production_read_only.py").read_text(
        encoding="utf-8"
    ).lower()
    forbidden = (
        "requests.", "httpx.", "urllib.", "kabustationclient", "brokeradapter",
        "sendorder", "send_order", ".post(", ".put(", ".request(",
        "mark_submitted", "kabu_station_api_password",
    )
    for token in forbidden:
        assert token not in source
