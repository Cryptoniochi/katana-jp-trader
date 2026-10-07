from dataclasses import dataclass
from pathlib import Path

from app.live.live_fault_tolerance_execution_gate import (
    ProductionFaultToleranceExecutionGate,
    ProductionFaultToleranceExecutionGateDecision,
)


@dataclass
class RuntimeStub:
    calls: int = 0
    result: object = None

    def run_once(self):
        self.calls += 1
        return self.result


def test_default_is_fail_closed_and_does_not_execute_runtime():
    runtime = RuntimeStub()
    gate = ProductionFaultToleranceExecutionGate(runtime=runtime)
    result = gate.run_once()
    assert result.decision is ProductionFaultToleranceExecutionGateDecision.BLOCKED
    assert result.allowed is False
    assert result.executed is False
    assert result.execution is None
    assert runtime.calls == 0


def test_explicit_false_is_blocked():
    runtime = RuntimeStub()
    gate = ProductionFaultToleranceExecutionGate(
        runtime=runtime,
        authorization_provider=lambda: False,
    )
    result = gate.run_once()
    assert result.allowed is False
    assert runtime.calls == 0


def test_truthy_non_bool_is_blocked():
    runtime = RuntimeStub()
    gate = ProductionFaultToleranceExecutionGate(
        runtime=runtime,
        authorization_provider=lambda: 1,
    )
    result = gate.run_once()
    assert result.allowed is False
    assert runtime.calls == 0


def test_provider_exception_fails_closed():
    runtime = RuntimeStub()

    def explode():
        raise RuntimeError("authorization unavailable")

    gate = ProductionFaultToleranceExecutionGate(
        runtime=runtime,
        authorization_provider=explode,
    )
    result = gate.run_once()
    assert result.allowed is False
    assert result.execution is None
    assert runtime.calls == 0
    assert "failed closed" in result.message


def test_literal_true_allows_exactly_one_runtime_execution():
    sentinel = object()
    runtime = RuntimeStub(result=sentinel)
    gate = ProductionFaultToleranceExecutionGate(
        runtime=runtime,
        authorization_provider=lambda: True,
    )
    result = gate.run_once()
    assert result.decision is ProductionFaultToleranceExecutionGateDecision.ALLOWED
    assert result.allowed is True
    assert result.executed is True
    assert result.execution is sentinel
    assert runtime.calls == 1


def test_construction_is_inert():
    calls = {"authorization": 0}

    def provider():
        calls["authorization"] += 1
        return True

    runtime = RuntimeStub()
    ProductionFaultToleranceExecutionGate(
        runtime=runtime,
        authorization_provider=provider,
    )
    assert calls["authorization"] == 0
    assert runtime.calls == 0


def test_gate_is_not_wired_into_existing_runtime_paths():
    token = "ProductionFaultToleranceExecutionGate"
    targets = (
        Path("app/runtime/paper_trading_composition.py"),
        Path("app/live/live_fault_tolerance_runtime.py"),
        Path("app/live/live_fault_tolerance_runtime_composition.py"),
        Path("app/live/live_fault_tolerance_runtime_recovery_composition.py"),
        Path("app/run_live_dry_run_operator.py"),
    )
    for target in targets:
        assert token not in target.read_text(encoding="utf-8")


def test_gate_has_no_scheduler_network_or_live_unlock_path():
    source = Path("app/live/live_fault_tolerance_execution_gate.py").read_text(
        encoding="utf-8"
    ).lower()
    forbidden = (
        "requests.",
        "httpx.",
        "urllib.",
        "threading",
        "asyncio",
        "while true",
        "while 1",
        "schedule.",
        "timer(",
        "sleep(",
        "manual_kill_switch",
        ".release(",
        "live_order_transmission_enabled = true",
        "live_broker_transport_enabled = true",
        "locked_live_runtime_integration_enabled = true",
        "sendorder",
        "send_order",
    )
    assert all(token not in source for token in forbidden)
