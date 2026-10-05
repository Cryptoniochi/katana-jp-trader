from __future__ import annotations

import inspect
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.live.live_fault_tolerance_persistence_boundary import (
    FaultToleranceAttemptPersistenceBoundary,
)
from app.live.live_fault_tolerance_saved_state_reader import FaultToleranceSavedStateReader
from app.live.live_fault_tolerance_saved_state_writer import FaultToleranceSavedStateWriter
from app.supervisor.fault_tolerance_models import (
    FaultToleranceAttempt,
    FaultToleranceDecision,
)
from app.supervisor.supervisor_models import (
    SupervisorSnapshot,
    SupervisorStatus,
)


NOW = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)


def _snapshot() -> SupervisorSnapshot:
    return SupervisorSnapshot(
        worker_name="paper-trading",
        status=SupervisorStatus.RUNNING,
        started_at=NOW,
        checked_at=NOW,
        last_heartbeat_at=NOW,
        last_restart_at=None,
        restart_count=0,
        stop_reason=None,
        message=None,
    )


def _attempt(
    decision: FaultToleranceDecision = FaultToleranceDecision.NO_ACTION,
) -> FaultToleranceAttempt:
    snapshot = _snapshot()
    return FaultToleranceAttempt(
        attempt_number=1,
        checked_at=NOW,
        decision=decision,
        supervisor_before=snapshot,
        supervisor_after=snapshot,
        recovery_result=None,
        consecutive_failure_count=0,
        next_action_at=None,
        message="completed production fault-tolerance attempt",
    )


def test_boundary_persists_exact_completed_attempt(tmp_path):
    path = tmp_path / "fault_tolerance_state.json"
    boundary = FaultToleranceAttemptPersistenceBoundary(
        writer=FaultToleranceSavedStateWriter(path)
    )
    attempt = _attempt()
    result = boundary.persist(attempt)

    assert result.attempt is attempt
    assert result.saved_state.attempt_number == attempt.attempt_number
    assert result.saved_state.checked_at == attempt.checked_at
    assert result.saved_state.decision is attempt.decision
    assert path.exists()


def test_persisted_state_is_readable_by_existing_read_only_provider(tmp_path):
    path = tmp_path / "fault_tolerance_state.json"
    boundary = FaultToleranceAttemptPersistenceBoundary(
        writer=FaultToleranceSavedStateWriter(path)
    )
    attempt = _attempt()
    boundary.persist(attempt)

    # The saved-state reader intentionally does not reconstruct the full
    # FaultToleranceAttempt. Its callable interface is the production
    # read-only contract used by LiveRuntimeReadOnlyProviderFactory.
    view = FaultToleranceSavedStateReader(path)()
    assert view is not None
    assert view.checked_at == attempt.checked_at
    assert view.decision is attempt.decision


def test_boundary_rejects_non_attempt_without_creating_state(tmp_path):
    path = tmp_path / "fault_tolerance_state.json"
    boundary = FaultToleranceAttemptPersistenceBoundary(
        writer=FaultToleranceSavedStateWriter(path)
    )
    with pytest.raises(TypeError):
        boundary.persist(object())
    assert not path.exists()


def test_boundary_does_not_execute_fault_tolerance_or_recovery():
    source = inspect.getsource(FaultToleranceAttemptPersistenceBoundary)
    forbidden = (
        "run_once(",
        ".recover(",
        ".stop(",
        ".mark_restarted(",
        "FaultToleranceService(",
    )
    assert all(token not in source for token in forbidden)


def test_boundary_contains_no_live_transport_or_network_primitives():
    source = Path(
        "app/live/live_fault_tolerance_persistence_boundary.py"
    ).read_text(encoding="utf-8").lower()
    forbidden = (
        "sendorder",
        "send_order",
        "requests.",
        "httpx.",
        "urllib.",
        "kabustationclient",
        "brokeradapter",
        "mark_submitted",
    )
    assert all(token not in source for token in forbidden)


def test_boundary_does_not_reference_manual_kill_switch_release():
    source = Path(
        "app/live/live_fault_tolerance_persistence_boundary.py"
    ).read_text(encoding="utf-8").lower()
    assert "manual_kill_switch" not in source
    assert ".release(" not in source
