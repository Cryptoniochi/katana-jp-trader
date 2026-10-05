"""Phase 6-D durable fault-tolerance state tests."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from app.live.live_fault_tolerance_saved_state import SavedFaultToleranceState
from app.live.live_fault_tolerance_saved_state_reader import (
    FaultToleranceSavedStateReader,
)
from app.live.live_fault_tolerance_saved_state_writer import (
    FaultToleranceSavedStateWriter,
)
from app.supervisor.fault_tolerance_models import FaultToleranceDecision


NOW = datetime(2026, 10, 5, 5, 30, tzinfo=timezone.utc)


def _state(
    decision: FaultToleranceDecision = FaultToleranceDecision.SAFE_STOP,
) -> SavedFaultToleranceState:
    return SavedFaultToleranceState(
        attempt_number=7,
        checked_at=NOW,
        decision=decision,
        consecutive_failure_count=3,
        message="operator attention required",
    )


def test_missing_file_returns_none(tmp_path) -> None:
    reader = FaultToleranceSavedStateReader(tmp_path / "missing.json")

    assert reader.read_state() is None
    assert reader() is None


def test_state_round_trip(tmp_path) -> None:
    path = tmp_path / "fault_tolerance.json"
    writer = FaultToleranceSavedStateWriter(path)
    reader = FaultToleranceSavedStateReader(path)

    writer.write(_state())

    assert reader.read_state() == _state()


def test_safe_stop_is_exposed_without_age_expiry(tmp_path) -> None:
    path = tmp_path / "fault_tolerance.json"
    FaultToleranceSavedStateWriter(path).write(_state())

    attempt = FaultToleranceSavedStateReader(path)()

    assert attempt is not None
    assert attempt.checked_at == NOW
    assert attempt.decision is FaultToleranceDecision.SAFE_STOP


def test_non_safe_stop_decision_is_preserved(tmp_path) -> None:
    path = tmp_path / "fault_tolerance.json"
    state = _state(FaultToleranceDecision.RECOVERED)
    FaultToleranceSavedStateWriter(path).write(state)

    attempt = FaultToleranceSavedStateReader(path)()

    assert attempt is not None
    assert attempt.decision is FaultToleranceDecision.RECOVERED


def test_corrupt_json_raises(tmp_path) -> None:
    path = tmp_path / "fault_tolerance.json"
    path.write_text("{", encoding="utf-8")

    with pytest.raises(json.JSONDecodeError):
        FaultToleranceSavedStateReader(path).read_state()


def test_unknown_schema_raises(tmp_path) -> None:
    path = tmp_path / "fault_tolerance.json"
    payload = {
        "attempt_number": 1,
        "checked_at": NOW.isoformat(),
        "decision": "safe_stop",
        "consecutive_failure_count": 1,
        "message": "blocked",
        "unexpected": True,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="invalid schema"):
        FaultToleranceSavedStateReader(path).read_state()


def test_naive_checked_at_raises(tmp_path) -> None:
    path = tmp_path / "fault_tolerance.json"
    payload = {
        "attempt_number": 1,
        "checked_at": "2026-10-05T05:30:00",
        "decision": "safe_stop",
        "consecutive_failure_count": 1,
        "message": "blocked",
    }
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="timezone-aware"):
        FaultToleranceSavedStateReader(path).read_state()


def test_boolean_integer_field_is_rejected(tmp_path) -> None:
    path = tmp_path / "fault_tolerance.json"
    payload = {
        "attempt_number": True,
        "checked_at": NOW.isoformat(),
        "decision": "safe_stop",
        "consecutive_failure_count": 1,
        "message": "blocked",
    }
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="attempt_number"):
        FaultToleranceSavedStateReader(path).read_state()


def test_writer_replaces_existing_state(tmp_path) -> None:
    path = tmp_path / "fault_tolerance.json"
    writer = FaultToleranceSavedStateWriter(path)

    writer.write(_state(FaultToleranceDecision.SAFE_STOP))
    writer.write(_state(FaultToleranceDecision.RECOVERED))

    state = FaultToleranceSavedStateReader(path).read_state()

    assert state is not None
    assert state.decision is FaultToleranceDecision.RECOVERED
    assert list(tmp_path.glob("*.tmp")) == []
