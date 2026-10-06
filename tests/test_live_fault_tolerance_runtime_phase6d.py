from pathlib import Path

import pytest

from app.live.live_fault_tolerance_runtime import (
    ProductionFaultToleranceRuntime,
    ProductionFaultToleranceRuntimeBundle,
)
from app.live.live_fault_tolerance_runtime_composition import ProductionFaultToleranceRuntimeFactory
from app.supervisor.supervisor_models import SupervisorStopReason


class SpyLifecycle:
    def __init__(self):
        self.is_running = False
        self.start_calls = self.heartbeat_calls = self.run_calls = self.stop_calls = 0
        self.last_heartbeat_at = self.last_stop_reason = self.last_stop_message = None
        self.start_result = object()
        self.heartbeat_result = object()
        self.run_result = object()
        self.stop_result = object()

    def start(self):
        self.start_calls += 1
        self.is_running = True
        return self.start_result

    def heartbeat(self, *, occurred_at=None):
        self.heartbeat_calls += 1
        self.last_heartbeat_at = occurred_at
        return self.heartbeat_result

    def run_once(self):
        self.run_calls += 1
        return self.run_result

    def stop(self, *, reason=SupervisorStopReason.MANUAL, message=None):
        self.stop_calls += 1
        self.last_stop_reason = reason
        self.last_stop_message = message
        self.is_running = False
        return self.stop_result


def make_runtime(lifecycle):
    return ProductionFaultToleranceRuntime(
        bundle=ProductionFaultToleranceRuntimeBundle(lifecycle=lifecycle)
    )


def test_runtime_construction_is_inert():
    lifecycle = SpyLifecycle()
    runtime = make_runtime(lifecycle)
    assert runtime.lifecycle is lifecycle
    assert runtime.is_running is False
    assert (lifecycle.start_calls, lifecycle.heartbeat_calls, lifecycle.run_calls, lifecycle.stop_calls) == (0, 0, 0, 0)


def test_factory_construction_is_inert():
    lifecycle = SpyLifecycle()
    runtime = ProductionFaultToleranceRuntimeFactory.create(lifecycle=lifecycle)
    assert runtime.lifecycle is lifecycle
    assert (lifecycle.start_calls, lifecycle.heartbeat_calls, lifecycle.run_calls, lifecycle.stop_calls) == (0, 0, 0, 0)


def test_runtime_explicitly_delegates_all_operations():
    lifecycle = SpyLifecycle()
    runtime = make_runtime(lifecycle)
    assert runtime.start() is lifecycle.start_result
    marker = object()
    assert runtime.heartbeat(occurred_at=marker) is lifecycle.heartbeat_result
    assert lifecycle.last_heartbeat_at is marker
    assert runtime.run_once() is lifecycle.run_result
    assert runtime.stop(reason=SupervisorStopReason.MANUAL, message="operator stop") is lifecycle.stop_result
    assert lifecycle.last_stop_reason is SupervisorStopReason.MANUAL
    assert lifecycle.last_stop_message == "operator stop"
    assert (lifecycle.start_calls, lifecycle.heartbeat_calls, lifecycle.run_calls, lifecycle.stop_calls) == (1, 1, 1, 1)


def test_run_once_does_not_auto_start_stop_or_heartbeat():
    lifecycle = SpyLifecycle()
    make_runtime(lifecycle).run_once()
    assert lifecycle.run_calls == 1
    assert (lifecycle.start_calls, lifecycle.heartbeat_calls, lifecycle.stop_calls) == (0, 0, 0)


def test_step6cj_is_not_wired_into_paper_or_dry_run():
    targets = (
        Path("app/runtime/paper_trading_composition.py"),
        Path("app/runtime/paper_trading_runtime.py"),
        Path("app/run_live_dry_run_operator.py"),
    )
    for target in targets:
        source = target.read_text(encoding="utf-8")
        assert "ProductionFaultToleranceRuntime" not in source
        assert "ProductionFaultToleranceRuntimeFactory" not in source


@pytest.mark.parametrize("target", (
    Path("app/live/live_fault_tolerance_runtime.py"),
    Path("app/live/live_fault_tolerance_runtime_composition.py"),
))
def test_runtime_boundary_has_no_scheduler_network_or_live_unlock(target):
    source = target.read_text(encoding="utf-8").lower()
    forbidden = (
        "threading", "asyncio", "while true", "while 1", "schedule.", "timer(",
        "sleep(", "sendorder", "send_order", "requests.", "httpx.", "urllib.",
        "brokeradapter", "mark_submitted", "manual_kill_switch", ".release(",
        "live_order_transmission_enabled = true",
        "live_broker_transport_enabled = true",
        "locked_live_runtime_integration_enabled = true",
    )
    assert all(token not in source for token in forbidden)


def test_runtime_composition_does_not_construct_operational_dependencies():
    source = Path("app/live/live_fault_tolerance_runtime_composition.py").read_text(encoding="utf-8")
    forbidden = (
        "RecoveryManager(", "FaultToleranceService(", "SupervisorService(",
        "FaultToleranceSavedStateWriter(", "ProductionFaultToleranceOwnerLifecycle(",
    )
    assert all(token not in source for token in forbidden)
