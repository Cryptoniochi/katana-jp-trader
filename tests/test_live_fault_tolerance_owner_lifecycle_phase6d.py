from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.live.live_fault_tolerance_owner_lifecycle import (
    FaultToleranceOwnerLifecycleState,
    ProductionFaultToleranceOwnerLifecycle,
)
from app.supervisor.supervisor_models import (
    SupervisorSnapshot,
    SupervisorStatus,
    SupervisorStopReason,
)


NOW = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)


def snapshot(
    *,
    status: SupervisorStatus,
    stop_reason: SupervisorStopReason | None,
) -> SupervisorSnapshot:
    return SupervisorSnapshot(
        worker_name="production-fault-tolerance-owner",
        status=status,
        started_at=NOW,
        checked_at=NOW,
        last_heartbeat_at=NOW,
        last_restart_at=None,
        restart_count=0,
        stop_reason=stop_reason,
        message=None,
    )


class SpySupervisor:
    def __init__(self) -> None:
        self.start_calls = 0
        self.heartbeat_calls = 0
        self.stop_calls = 0
        self.last_heartbeat_at = None
        self.last_stop_reason = None
        self.last_stop_message = None

    def start(self):
        self.start_calls += 1
        return snapshot(
            status=SupervisorStatus.RUNNING,
            stop_reason=None,
        )

    def record_heartbeat(self, *, occurred_at=None):
        self.heartbeat_calls += 1
        self.last_heartbeat_at = occurred_at
        return snapshot(
            status=SupervisorStatus.RUNNING,
            stop_reason=None,
        )

    def stop(
        self,
        *,
        reason=SupervisorStopReason.MANUAL,
        message=None,
    ):
        self.stop_calls += 1
        self.last_stop_reason = reason
        self.last_stop_message = message
        status = (
            SupervisorStatus.STOPPED
            if reason in {
                SupervisorStopReason.NORMAL,
                SupervisorStopReason.MANUAL,
            }
            else SupervisorStatus.FAILED
        )
        return snapshot(status=status, stop_reason=reason)


class SpyOwner:
    def __init__(self) -> None:
        self.supervisor = SpySupervisor()
        self.run_calls = 0
        self.result = object()

    def run_once(self):
        self.run_calls += 1
        return self.result


def test_construction_is_stopped_and_inert():
    owner = SpyOwner()
    lifecycle = ProductionFaultToleranceOwnerLifecycle(owner=owner)

    assert lifecycle.state is FaultToleranceOwnerLifecycleState.STOPPED
    assert lifecycle.is_running is False
    assert owner.supervisor.start_calls == 0
    assert owner.supervisor.heartbeat_calls == 0
    assert owner.supervisor.stop_calls == 0
    assert owner.run_calls == 0


def test_start_is_explicit_and_starts_supervisor_once():
    owner = SpyOwner()
    lifecycle = ProductionFaultToleranceOwnerLifecycle(owner=owner)

    result = lifecycle.start()

    assert result.state is FaultToleranceOwnerLifecycleState.RUNNING
    assert result.supervisor.status is SupervisorStatus.RUNNING
    assert lifecycle.is_running is True
    assert owner.supervisor.start_calls == 1
    assert owner.run_calls == 0


def test_duplicate_start_fails_without_second_supervisor_start():
    owner = SpyOwner()
    lifecycle = ProductionFaultToleranceOwnerLifecycle(owner=owner)
    lifecycle.start()

    with pytest.raises(RuntimeError, match="already running"):
        lifecycle.start()

    assert owner.supervisor.start_calls == 1


def test_heartbeat_requires_start_and_delegates_after_start():
    owner = SpyOwner()
    lifecycle = ProductionFaultToleranceOwnerLifecycle(owner=owner)

    with pytest.raises(RuntimeError, match="before heartbeat"):
        lifecycle.heartbeat(occurred_at=NOW)

    lifecycle.start()
    result = lifecycle.heartbeat(occurred_at=NOW)

    assert result.state is FaultToleranceOwnerLifecycleState.RUNNING
    assert owner.supervisor.heartbeat_calls == 1
    assert owner.supervisor.last_heartbeat_at == NOW


def test_run_once_requires_start_and_delegates_exactly_once():
    owner = SpyOwner()
    lifecycle = ProductionFaultToleranceOwnerLifecycle(owner=owner)

    with pytest.raises(RuntimeError, match="before run_once"):
        lifecycle.run_once()

    lifecycle.start()
    result = lifecycle.run_once()

    assert result is owner.result
    assert owner.run_calls == 1
    assert owner.supervisor.heartbeat_calls == 0


def test_stop_requires_start_and_is_explicit():
    owner = SpyOwner()
    lifecycle = ProductionFaultToleranceOwnerLifecycle(owner=owner)

    with pytest.raises(RuntimeError, match="before stop"):
        lifecycle.stop()

    lifecycle.start()
    result = lifecycle.stop(
        reason=SupervisorStopReason.MANUAL,
        message="operator stop",
    )

    assert result.state is FaultToleranceOwnerLifecycleState.STOPPED
    assert result.supervisor.status is SupervisorStatus.STOPPED
    assert lifecycle.is_running is False
    assert owner.supervisor.stop_calls == 1
    assert owner.supervisor.last_stop_reason is SupervisorStopReason.MANUAL
    assert owner.supervisor.last_stop_message == "operator stop"


def test_run_once_is_blocked_again_after_stop():
    owner = SpyOwner()
    lifecycle = ProductionFaultToleranceOwnerLifecycle(owner=owner)
    lifecycle.start()
    lifecycle.stop()

    with pytest.raises(RuntimeError, match="before run_once"):
        lifecycle.run_once()

    assert owner.run_calls == 0


def test_lifecycle_does_not_implicitly_heartbeat_around_run_once():
    owner = SpyOwner()
    lifecycle = ProductionFaultToleranceOwnerLifecycle(owner=owner)
    lifecycle.start()

    lifecycle.run_once()

    assert owner.run_calls == 1
    assert owner.supervisor.heartbeat_calls == 0


def test_step6ci_is_not_wired_into_paper_runtime_or_dry_run():
    targets = (
        Path("app/runtime/paper_trading_composition.py"),
        Path("app/runtime/paper_trading_runtime.py"),
        Path("app/run_live_dry_run_operator.py"),
    )
    forbidden = (
        "ProductionFaultToleranceOwnerLifecycle",
        "FaultToleranceOwnerLifecycleState",
    )
    for target in targets:
        source = target.read_text(encoding="utf-8")
        assert all(token not in source for token in forbidden)


def test_lifecycle_contains_no_scheduler_network_or_live_unlock():
    source = Path(
        "app/live/live_fault_tolerance_owner_lifecycle.py"
    ).read_text(encoding="utf-8").lower()
    forbidden = (
        "threading",
        "asyncio",
        "while true",
        "while 1",
        "schedule.",
        "timer(",
        "sleep(",
        "sendorder",
        "send_order",
        "requests.",
        "httpx.",
        "urllib.",
        "brokeradapter",
        "mark_submitted",
        "manual_kill_switch",
        ".release(",
        "live_order_transmission_enabled = true",
        "live_broker_transport_enabled = true",
        "locked_live_runtime_integration_enabled = true",
    )
    assert all(token not in source for token in forbidden)
