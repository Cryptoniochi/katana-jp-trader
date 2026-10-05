from __future__ import annotations

from pathlib import Path

from app.live.live_fault_tolerance_owner_composition import (
    ProductionFaultToleranceOwnerFactory,
)


class SpySupervisor:
    def __init__(self) -> None:
        self.start_calls = 0
        self.heartbeat_calls = 0
        self.check_calls = 0

    def start(self):
        self.start_calls += 1

    def record_heartbeat(self, *, occurred_at=None):
        self.heartbeat_calls += 1

    def check(self):
        self.check_calls += 1


class SpyExecutionBoundary:
    def __init__(self, result=object()) -> None:
        self.result = result
        self.execute_calls = 0

    def execute_once(self):
        self.execute_calls += 1
        return self.result


def test_factory_construction_is_completely_inert():
    supervisor = SpySupervisor()
    execution = SpyExecutionBoundary()

    owner = ProductionFaultToleranceOwnerFactory.create(
        supervisor=supervisor,
        execution_boundary=execution,
    )

    assert owner.supervisor is supervisor
    assert owner.execution_boundary is execution
    assert supervisor.start_calls == 0
    assert supervisor.heartbeat_calls == 0
    assert supervisor.check_calls == 0
    assert execution.execute_calls == 0


def test_owner_run_once_delegates_exactly_once_without_hidden_lifecycle():
    supervisor = SpySupervisor()
    expected = object()
    execution = SpyExecutionBoundary(expected)

    owner = ProductionFaultToleranceOwnerFactory.create(
        supervisor=supervisor,
        execution_boundary=execution,
    )
    result = owner.run_once()

    assert result is expected
    assert execution.execute_calls == 1
    assert supervisor.start_calls == 0
    assert supervisor.heartbeat_calls == 0
    assert supervisor.check_calls == 0


def test_step6ch_does_not_wire_owner_into_paper_runtime_or_dry_run():
    targets = (
        Path("app/runtime/paper_trading_composition.py"),
        Path("app/runtime/paper_trading_runtime.py"),
        Path("app/run_live_dry_run_operator.py"),
    )
    forbidden = (
        "ProductionFaultToleranceOwner",
        "ProductionFaultToleranceOwnerFactory",
    )
    for target in targets:
        source = target.read_text(encoding="utf-8")
        assert all(token not in source for token in forbidden)


def test_owner_and_composition_have_no_scheduler_or_background_loop():
    source = (
        Path("app/live/live_fault_tolerance_owner.py").read_text(encoding="utf-8")
        + Path("app/live/live_fault_tolerance_owner_composition.py").read_text(
            encoding="utf-8"
        )
    ).lower()
    forbidden = (
        "threading",
        "asyncio",
        "while true",
        "while 1",
        "schedule.",
        "timer(",
        "sleep(",
    )
    assert all(token not in source for token in forbidden)


def test_composition_does_not_construct_recovery_or_fault_tolerance_service():
    source = Path(
        "app/live/live_fault_tolerance_owner_composition.py"
    ).read_text(encoding="utf-8")
    assert "RecoveryManager(" not in source
    assert "FaultToleranceService(" not in source
    assert "SupervisorService(" not in source


def test_owner_does_not_start_or_mutate_supervisor_implicitly():
    source = Path(
        "app/live/live_fault_tolerance_owner.py"
    ).read_text(encoding="utf-8")
    assert ".start(" not in source
    assert ".record_heartbeat(" not in source
    assert ".stop(" not in source
    assert ".mark_restarted(" not in source


def test_owner_boundary_contains_no_live_transport_or_manual_release():
    source = (
        Path("app/live/live_fault_tolerance_owner.py").read_text(encoding="utf-8")
        + Path("app/live/live_fault_tolerance_owner_composition.py").read_text(
            encoding="utf-8"
        )
    ).lower()
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
