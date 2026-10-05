from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.live.live_dry_run_safety_diagnostic import ProductionSafetyDiagnostic, ProductionSafetyDiagnosticPaths
from app.run_live_dry_run_safety_diagnostic import format_report

NOW = datetime(2026, 10, 5, 7, 0, tzinfo=timezone.utc)


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _paths(tmp_path: Path) -> ProductionSafetyDiagnosticPaths:
    return ProductionSafetyDiagnosticPaths(
        runtime_status=tmp_path / "runtime.json",
        kabu_station=tmp_path / "kabu.json",
        reconciliation=tmp_path / "reconciliation.json",
        fault_tolerance=tmp_path / "fault.json",
        manual_kill_switch=tmp_path / "manual.json",
    )


def _seed_ready(paths: ProductionSafetyDiagnosticPaths) -> None:
    stamp = (NOW - timedelta(seconds=10)).isoformat()
    _write(paths.runtime_status, {"available": True, "state": "running", "generated_at": stamp})
    _write(paths.kabu_station, {"connected": True, "generated_at": stamp})
    _write(paths.reconciliation, {"consistent": True, "state": "consistent", "generated_at": stamp})
    _write(paths.fault_tolerance, {"checked_at": stamp, "decision": "no_action"})
    _write(paths.manual_kill_switch, {"manual_blocked": False, "reason": "test release"})


def test_ready_saved_inputs_still_keep_transport_and_live_order_closed(tmp_path):
    paths = _paths(tmp_path)
    _seed_ready(paths)
    report = ProductionSafetyDiagnostic(paths=paths, now_provider=lambda: NOW).check()
    assert report.activation_inputs_ready is True
    assert report.transport_ready is False
    assert report.live_order_ready is False
    assert all(item.passed for item in report.items)


def test_missing_fault_tolerance_fails_closed(tmp_path):
    paths = _paths(tmp_path)
    _seed_ready(paths)
    paths.fault_tolerance.unlink()
    report = ProductionSafetyDiagnostic(paths=paths, now_provider=lambda: NOW).check()
    item = next(x for x in report.items if x.key == "fault_tolerance")
    assert item.passed is False
    assert "missing" in item.message
    assert report.activation_inputs_ready is False


def test_completed_runtime_is_explained_as_blocked(tmp_path):
    paths = _paths(tmp_path)
    _seed_ready(paths)
    _write(paths.runtime_status, {"available": True, "state": "completed", "generated_at": NOW.isoformat()})
    report = ProductionSafetyDiagnostic(paths=paths, now_provider=lambda: NOW).check()
    item = next(x for x in report.items if x.key == "paper_runtime")
    assert item.passed is False
    assert "completed" in item.message


def test_stale_reconciliation_is_explained_as_blocked(tmp_path):
    paths = _paths(tmp_path)
    _seed_ready(paths)
    _write(paths.reconciliation, {"consistent": True, "state": "consistent", "generated_at": (NOW - timedelta(minutes=10)).isoformat()})
    report = ProductionSafetyDiagnostic(paths=paths, now_provider=lambda: NOW).check()
    item = next(x for x in report.items if x.key == "reconciliation")
    assert item.passed is False
    assert "stale" in item.message


def test_manual_kill_switch_block_is_explained(tmp_path):
    paths = _paths(tmp_path)
    _seed_ready(paths)
    _write(paths.manual_kill_switch, {"manual_blocked": True, "reason": "operator block"})
    report = ProductionSafetyDiagnostic(paths=paths, now_provider=lambda: NOW).check()
    item = next(x for x in report.items if x.key == "manual_kill_switch")
    assert item.passed is False


def test_formatted_output_states_no_transmission(tmp_path):
    paths = _paths(tmp_path)
    _seed_ready(paths)
    text = format_report(ProductionSafetyDiagnostic(paths=paths, now_provider=lambda: NOW).check())
    assert "broker_transmission_occurred=false" in text
    assert "transport_ready=false" in text
    assert "live_order_ready=false" in text


def test_production_module_contains_no_network_recovery_or_submission_primitives():
    source = Path("app/live/live_dry_run_safety_diagnostic.py").read_text(encoding="utf-8").lower()
    forbidden = ("sendorder", "send_order", "requests.", "httpx.", "urllib.", "kabustationclient", "brokeradapter", "mark_submitted", ".recover(", "run_once(")
    assert all(token not in source for token in forbidden)
