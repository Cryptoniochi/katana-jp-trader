from __future__ import annotations

import inspect
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.live.live_fault_tolerance_execution_boundary import (
    ProductionFaultToleranceExecutionBoundary,
)
from app.live.live_fault_tolerance_persistence_boundary import (
    FaultToleranceAttemptPersistenceBoundary,
)
from app.live.live_fault_tolerance_saved_state_reader import (
    FaultToleranceSavedStateReader,
)
from app.live.live_fault_tolerance_saved_state_writer import (
    FaultToleranceSavedStateWriter,
)
from app.supervisor.fault_tolerance_models import (
    FaultToleranceAttempt,
    FaultToleranceDecision,
)
from app.supervisor.supervisor_models import SupervisorSnapshot, SupervisorStatus


NOW = datetime(2026, 10, 5, 12, 30, tzinfo=timezone.utc)


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


def _attempt() -> FaultToleranceAttempt:
    snapshot = _snapshot()
    return FaultToleranceAttempt(
        attempt_number=7,
        checked_at=NOW,
        decision=FaultToleranceDecision.NO_ACTION,
        supervisor_before=snapshot,
        supervisor_after=snapshot,
        recovery_result=None,
        consecutive_failure_count=0,
        next_action_at=None,
        message="completed by owning fault-tolerance service",
    )


class StubFaultToleranceService:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    def run_once(self):
        self.calls += 1
        return self.result


class ExplodingFaultToleranceService:
    def run_once(self):
        raise RuntimeError("fault-tolerance execution failed")


def test_execute_once_runs_owner_once_then_persists_exact_attempt(tmp_path):
    path = tmp_path / "fault_tolerance_state.json"
    attempt = _attempt()
    service = StubFaultToleranceService(attempt)
    boundary = ProductionFaultToleranceExecutionBoundary(
        service=service,
        persistence_boundary=FaultToleranceAttemptPersistenceBoundary(
            writer=FaultToleranceSavedStateWriter(path)
        ),
    )

    result = boundary.execute_once()

    assert service.calls == 1
    assert result.attempt is attempt
    assert result.persistence.attempt is attempt
    assert path.exists()

    view = FaultToleranceSavedStateReader(path)()
    assert view is not None
    assert view.checked_at == attempt.checked_at
    assert view.decision is attempt.decision


def test_failed_execution_is_not_persisted(tmp_path):
    path = tmp_path / "fault_tolerance_state.json"
    boundary = ProductionFaultToleranceExecutionBoundary(
        service=ExplodingFaultToleranceService(),
        persistence_boundary=FaultToleranceAttemptPersistenceBoundary(
            writer=FaultToleranceSavedStateWriter(path)
        ),
    )

    with pytest.raises(RuntimeError, match="fault-tolerance execution failed"):
        boundary.execute_once()

    assert not path.exists()


def test_non_attempt_result_is_rejected_without_persistence(tmp_path):
    path = tmp_path / "fault_tolerance_state.json"
    service = StubFaultToleranceService(object())
    boundary = ProductionFaultToleranceExecutionBoundary(
        service=service,
        persistence_boundary=FaultToleranceAttemptPersistenceBoundary(
            writer=FaultToleranceSavedStateWriter(path)
        ),
    )

    with pytest.raises(TypeError):
        boundary.execute_once()

    assert service.calls == 1
    assert not path.exists()


def test_construction_is_inert(tmp_path):
    path = tmp_path / "fault_tolerance_state.json"
    service = StubFaultToleranceService(_attempt())

    ProductionFaultToleranceExecutionBoundary(
        service=service,
        persistence_boundary=FaultToleranceAttemptPersistenceBoundary(
            writer=FaultToleranceSavedStateWriter(path)
        ),
    )

    assert service.calls == 0
    assert not path.exists()


def test_step6cg_does_not_wire_execution_into_paper_or_dry_run():
    paper_source = Path(
        "app/runtime/paper_trading_composition.py"
    ).read_text(encoding="utf-8")
    dry_run_source = Path(
        "app/run_live_dry_run_operator.py"
    ).read_text(encoding="utf-8")

    assert "ProductionFaultToleranceExecutionBoundary" not in paper_source
    assert "FaultToleranceService(" not in paper_source
    assert "ProductionFaultToleranceExecutionBoundary" not in dry_run_source
    assert "FaultToleranceService(" not in dry_run_source


def test_execution_boundary_contains_no_live_transport_or_manual_release():
    source = Path(
        "app/live/live_fault_tolerance_execution_boundary.py"
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
        "manual_kill_switch",
        ".release(",
    )
    assert all(token not in source for token in forbidden)


def test_execution_boundary_only_exposes_explicit_execute_once_trigger():
    source = inspect.getsource(ProductionFaultToleranceExecutionBoundary)
    assert "def execute_once(" in source
    assert source.count(".run_once()") == 1
