from pathlib import Path

import pytest

from app.live.live_fault_tolerance_operator_boundary import (
    ProductionFaultToleranceOperatorBoundary,
)
from app.supervisor.supervisor_models import SupervisorStopReason


class SpyRuntime:
    def __init__(self, *, fail_at=None):
        self.fail_at = fail_at
        self.calls = []
        self.start_result = object()
        self.heartbeat_result = object()
        self.execution_result = object()
        self.stop_result = object()
        self.stop_reason = None
        self.stop_message = None

    def start(self):
        self.calls.append("start")
        if self.fail_at == "start":
            raise RuntimeError("start failed")
        return self.start_result

    def heartbeat(self, *, occurred_at=None):
        self.calls.append("heartbeat")
        if self.fail_at == "heartbeat":
            raise RuntimeError("heartbeat failed")
        return self.heartbeat_result

    def run_once(self):
        self.calls.append("run_once")
        if self.fail_at == "run_once":
            raise RuntimeError("run failed")
        return self.execution_result

    def stop(self, *, reason=SupervisorStopReason.MANUAL, message=None):
        self.calls.append("stop")
        self.stop_reason = reason
        self.stop_message = message
        if self.fail_at == "stop":
            raise RuntimeError("stop failed")
        return self.stop_result


def test_construction_is_inert():
    runtime = SpyRuntime()
    boundary = ProductionFaultToleranceOperatorBoundary(runtime=runtime)
    assert boundary.runtime is runtime
    assert runtime.calls == []


def test_successful_one_shot_has_explicit_order_and_results():
    runtime = SpyRuntime()
    result = ProductionFaultToleranceOperatorBoundary(runtime=runtime).run_once()

    assert runtime.calls == ["start", "heartbeat", "run_once", "stop"]
    assert result.start is runtime.start_result
    assert result.heartbeat is runtime.heartbeat_result
    assert result.execution is runtime.execution_result
    assert result.stop is runtime.stop_result
    assert runtime.stop_reason is SupervisorStopReason.NORMAL
    assert runtime.stop_message == "operator one-shot completed"


def test_start_failure_does_not_stop_unstarted_runtime():
    runtime = SpyRuntime(fail_at="start")
    with pytest.raises(RuntimeError, match="start failed"):
        ProductionFaultToleranceOperatorBoundary(runtime=runtime).run_once()
    assert runtime.calls == ["start"]


def test_heartbeat_failure_still_stops_runtime():
    runtime = SpyRuntime(fail_at="heartbeat")
    with pytest.raises(RuntimeError, match="heartbeat failed"):
        ProductionFaultToleranceOperatorBoundary(runtime=runtime).run_once()
    assert runtime.calls == ["start", "heartbeat", "stop"]


def test_execution_failure_still_stops_runtime():
    runtime = SpyRuntime(fail_at="run_once")
    with pytest.raises(RuntimeError, match="run failed"):
        ProductionFaultToleranceOperatorBoundary(runtime=runtime).run_once()
    assert runtime.calls == ["start", "heartbeat", "run_once", "stop"]


def test_stop_failure_is_not_silenced():
    runtime = SpyRuntime(fail_at="stop")
    with pytest.raises(RuntimeError, match="stop failed"):
        ProductionFaultToleranceOperatorBoundary(runtime=runtime).run_once()
    assert runtime.calls == ["start", "heartbeat", "run_once", "stop"]


def test_step6ck_is_not_wired_into_paper_or_live_dry_run_cli():
    targets = (
        Path("app/runtime/paper_trading_composition.py"),
        Path("app/runtime/paper_trading_runtime.py"),
        Path("app/run_live_dry_run_operator.py"),
    )
    for target in targets:
        source = target.read_text(encoding="utf-8")
        assert "ProductionFaultToleranceOperatorBoundary" not in source


def test_operator_boundary_has_no_scheduler_network_or_live_unlock():
    source = Path(
        "app/live/live_fault_tolerance_operator_boundary.py"
    ).read_text(encoding="utf-8").lower()
    forbidden = (
        "threading", "asyncio", "while true", "while 1", "schedule.", "timer(",
        "sleep(", "sendorder", "send_order", "requests.", "httpx.", "urllib.",
        "brokeradapter", "mark_submitted", "manual_kill_switch", ".release(",
        "live_order_transmission_enabled = true",
        "live_broker_transport_enabled = true",
        "locked_live_runtime_integration_enabled = true",
    )
    assert all(token not in source for token in forbidden)


def test_operator_boundary_does_not_construct_operational_dependencies():
    source = Path(
        "app/live/live_fault_tolerance_operator_boundary.py"
    ).read_text(encoding="utf-8")
    forbidden = (
        "RecoveryManager(",
        "FaultToleranceService(",
        "SupervisorService(",
        "FaultToleranceSavedStateWriter(",
        "ProductionFaultToleranceRuntime(",
    )
    assert all(token not in source for token in forbidden)
