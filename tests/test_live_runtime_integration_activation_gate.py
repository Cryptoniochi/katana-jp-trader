"""Tests for Phase 6-F Step 3 runtime integration activation gate."""
from __future__ import annotations

from datetime import datetime, timezone
import inspect

import pytest

import app.live.live_runtime_integration_activation_gate as gate_module
from app.live.live_broker_transport import LIVE_BROKER_TRANSPORT_ENABLED
from app.live.live_order_adapter import LIVE_ORDER_TRANSMISSION_ENABLED
from app.live.live_runtime_activation_boundary import (
    LiveRuntimeActivationDecision,
    LiveRuntimeActivationReport,
)
from app.live.live_runtime_integration_activation_gate import (
    LiveRuntimeIntegrationActivationGate,
    LiveRuntimeIntegrationGateDecision,
    LiveRuntimeIntegrationGateReport,
)
from app.live.locked_live_runtime_integration import (
    LOCKED_LIVE_RUNTIME_INTEGRATION_ENABLED,
)

NOW = datetime(2026, 10, 10, 3, 0, tzinfo=timezone.utc)


def _activation_report(*, ready: bool) -> LiveRuntimeActivationReport:
    return LiveRuntimeActivationReport(
        generated_at=NOW,
        decision=(
            LiveRuntimeActivationDecision.ACTIVATION_READY
            if ready
            else LiveRuntimeActivationDecision.BLOCKED
        ),
        runtime_activation_ready=ready,
        message="test activation report",
    )


def test_blocked_activation_report_keeps_gate_blocked():
    report = LiveRuntimeIntegrationActivationGate.evaluate(
        _activation_report(ready=False)
    )
    assert report.decision is LiveRuntimeIntegrationGateDecision.BLOCKED
    assert report.activation_prerequisites_ready is False
    assert report.legacy_hard_lock_closed is True


def test_ready_activation_report_only_reaches_reviewed_unlock_readiness():
    report = LiveRuntimeIntegrationActivationGate.evaluate(
        _activation_report(ready=True)
    )
    assert (
        report.decision
        is LiveRuntimeIntegrationGateDecision.READY_FOR_REVIEWED_UNLOCK
    )
    assert report.activation_prerequisites_ready is True
    assert report.legacy_hard_lock_closed is True
    assert "hard lock remains closed" in report.message


def test_open_legacy_hard_lock_fails_closed(monkeypatch):
    monkeypatch.setattr(
        gate_module,
        "LOCKED_LIVE_RUNTIME_INTEGRATION_ENABLED",
        True,
    )
    report = LiveRuntimeIntegrationActivationGate.evaluate(
        _activation_report(ready=True)
    )
    assert report.decision is LiveRuntimeIntegrationGateDecision.BLOCKED
    assert report.legacy_hard_lock_closed is False


def test_ready_report_rejects_missing_prerequisites():
    with pytest.raises(ValueError):
        LiveRuntimeIntegrationGateReport(
            NOW,
            LiveRuntimeIntegrationGateDecision.READY_FOR_REVIEWED_UNLOCK,
            False,
            True,
            "invalid",
        )


def test_ready_report_rejects_open_legacy_lock():
    with pytest.raises(ValueError):
        LiveRuntimeIntegrationGateReport(
            NOW,
            LiveRuntimeIntegrationGateDecision.READY_FOR_REVIEWED_UNLOCK,
            True,
            False,
            "invalid",
        )


def test_gate_keeps_all_execution_locks_closed():
    assert LOCKED_LIVE_RUNTIME_INTEGRATION_ENABLED is False
    assert LIVE_BROKER_TRANSPORT_ENABLED is False
    assert LIVE_ORDER_TRANSMISSION_ENABLED is False


def test_gate_does_not_import_or_reference_runtime_factory():
    source = inspect.getsource(gate_module)
    assert "FreshLockedLiveRuntimeFactory" not in source
    assert "LockedLiveRuntimeIntegration(" not in source


def test_gate_exposes_no_execution_side_effect_api():
    forbidden = {
        "unlock", "arm", "release", "recover", "start", "run", "process",
        "execute", "create", "build", "send", "send_order", "sendorder",
        "submit", "submit_order", "transmit",
    }
    assert forbidden.isdisjoint(dir(LiveRuntimeIntegrationActivationGate))
