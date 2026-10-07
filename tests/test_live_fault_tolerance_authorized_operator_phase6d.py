from dataclasses import dataclass
from pathlib import Path

import pytest

from app.live.live_fault_tolerance_authorized_operator import (
    ProductionFaultToleranceAuthorizedOperatorBoundary,
)
from app.live.live_fault_tolerance_authorized_operator_composition import (
    ProductionFaultToleranceAuthorizedOperatorFactory,
)
from app.live.live_fault_tolerance_execution_gate import (
    ProductionFaultToleranceExecutionGate,
)
from app.live.live_fault_tolerance_recovery_authorization import (
    ProductionFaultToleranceRecoveryAuthorizationProviders,
)


def providers(**overrides):
    values = {
        "manual_kill_switch_released": lambda: True,
        "runtime_healthy": lambda: True,
        "heartbeat_alive": lambda: True,
        "broker_available": lambda: True,
        "reconciliation_consistent": lambda: True,
    }
    values.update(overrides)
    return ProductionFaultToleranceRecoveryAuthorizationProviders(**values)


@dataclass
class RuntimeStub:
    events: list
    execution_result: object = None
    running: bool = False

    def start(self):
        self.events.append("start")
        self.running = True
        return "start-snapshot"

    def heartbeat(self):
        self.events.append("heartbeat")
        return "heartbeat-snapshot"

    def run_once(self):
        self.events.append("run_once")
        return self.execution_result

    def stop(self, *, reason, message=None):
        self.events.append("stop")
        self.running = False
        return "stop-snapshot"


def test_authorized_one_shot_order_is_start_heartbeat_gate_execution_stop():
    events = []
    sentinel = object()
    runtime = RuntimeStub(events=events, execution_result=sentinel)
    bundle = ProductionFaultToleranceAuthorizedOperatorFactory.create(
        runtime=runtime,
        providers=providers(),
    )
    result = bundle.operator.run_once()
    assert events == ["start", "heartbeat", "run_once", "stop"]
    assert result.gate.allowed is True
    assert result.gate.execution is sentinel
    assert result.start == "start-snapshot"
    assert result.heartbeat == "heartbeat-snapshot"
    assert result.stop == "stop-snapshot"
    assert runtime.running is False


def test_blocked_authorization_still_stops_without_execution():
    events = []
    runtime = RuntimeStub(events=events)
    bundle = ProductionFaultToleranceAuthorizedOperatorFactory.create(
        runtime=runtime,
        providers=providers(broker_available=lambda: False),
    )
    result = bundle.operator.run_once()
    assert events == ["start", "heartbeat", "stop"]
    assert result.gate.allowed is False
    assert result.gate.execution is None
    assert runtime.running is False


def test_authorization_exception_still_stops_without_execution():
    def explode():
        raise RuntimeError("read-only state unavailable")

    events = []
    runtime = RuntimeStub(events=events)
    bundle = ProductionFaultToleranceAuthorizedOperatorFactory.create(
        runtime=runtime,
        providers=providers(reconciliation_consistent=explode),
    )
    result = bundle.operator.run_once()
    assert events == ["start", "heartbeat", "stop"]
    assert result.gate.allowed is False
    assert runtime.running is False


def test_runtime_execution_exception_still_stops():
    class ExplodingRuntime(RuntimeStub):
        def run_once(self):
            self.events.append("run_once")
            raise RuntimeError("recovery failed")

    events = []
    runtime = ExplodingRuntime(events=events)
    bundle = ProductionFaultToleranceAuthorizedOperatorFactory.create(
        runtime=runtime,
        providers=providers(),
    )
    with pytest.raises(RuntimeError, match="recovery failed"):
        bundle.operator.run_once()
    assert events == ["start", "heartbeat", "run_once", "stop"]
    assert runtime.running is False


def test_factory_construction_is_inert():
    calls = {"provider": 0}

    def provider():
        calls["provider"] += 1
        return True

    events = []
    runtime = RuntimeStub(events=events)
    ProductionFaultToleranceAuthorizedOperatorFactory.create(
        runtime=runtime,
        providers=providers(runtime_healthy=provider),
    )
    assert events == []
    assert calls["provider"] == 0


def test_operator_rejects_gate_for_different_runtime():
    runtime_a = RuntimeStub(events=[])
    runtime_b = RuntimeStub(events=[])
    gate = ProductionFaultToleranceExecutionGate(
        runtime=runtime_b,
        authorization_provider=lambda: True,
    )
    with pytest.raises(ValueError, match="same runtime"):
        ProductionFaultToleranceAuthorizedOperatorBoundary(
            runtime=runtime_a,
            gate=gate,
        )


def test_operator_is_not_wired_into_existing_operational_paths():
    token = "ProductionFaultToleranceAuthorizedOperator"
    targets = (
        Path("app/runtime/paper_trading_composition.py"),
        Path("app/live/live_fault_tolerance_runtime.py"),
        Path("app/live/live_fault_tolerance_runtime_recovery_composition.py"),
        Path("app/run_live_dry_run_operator.py"),
    )
    for target in targets:
        assert token not in target.read_text(encoding="utf-8")


def test_operator_has_no_scheduler_network_or_live_unlock():
    source = Path(
        "app/live/live_fault_tolerance_authorized_operator.py"
    ).read_text(encoding="utf-8").lower()
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
        ".release(",
        "sendorder",
        "send_order",
        "live_order_transmission_enabled = true",
        "live_broker_transport_enabled = true",
        "locked_live_runtime_integration_enabled = true",
    )
    assert all(token not in source for token in forbidden)
