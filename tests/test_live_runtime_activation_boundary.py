"""Tests for Phase 6-F Step 2 runtime activation boundary."""
from __future__ import annotations
from datetime import datetime, timezone
import pytest
from app.live.live_activation_authorization import LiveActivationAuthorizationReport, LiveActivationAuthorizationState
from app.live.live_activation_transition import LiveActivationTransition
from app.live.live_broker_transport import LIVE_BROKER_TRANSPORT_ENABLED
from app.live.live_order_adapter import LIVE_ORDER_TRANSMISSION_ENABLED
from app.live.live_runtime_activation_boundary import LiveRuntimeActivationBoundary, LiveRuntimeActivationDecision, LiveRuntimeActivationReport
from app.live.locked_live_runtime_integration import LOCKED_LIVE_RUNTIME_INTEGRATION_ENABLED

NOW = datetime(2026, 10, 10, 2, 0, tzinfo=timezone.utc)

def _authorization_report(ready: bool) -> LiveActivationAuthorizationReport:
    return LiveActivationAuthorizationReport(
        generated_at=NOW, authorization_ready=ready,
        state=LiveActivationAuthorizationState.AUTHORIZATION_READY if ready else LiveActivationAuthorizationState.BLOCKED,
        items=(),
    )

def test_blocked_transition_keeps_runtime_activation_blocked():
    transition = LiveActivationTransition.evaluate(
        authorization_report=_authorization_report(False), runtime_prerequisites_ready=True)
    report = LiveRuntimeActivationBoundary.evaluate(transition)
    assert report.decision is LiveRuntimeActivationDecision.BLOCKED
    assert report.runtime_activation_ready is False

def test_authorization_ready_alone_does_not_activate_runtime():
    transition = LiveActivationTransition.evaluate(authorization_report=_authorization_report(True))
    report = LiveRuntimeActivationBoundary.evaluate(transition)
    assert report.decision is LiveRuntimeActivationDecision.BLOCKED

def test_runtime_transition_can_reach_read_only_activation_ready():
    transition = LiveActivationTransition.evaluate(
        authorization_report=_authorization_report(True), runtime_prerequisites_ready=True)
    report = LiveRuntimeActivationBoundary.evaluate(transition)
    assert report.decision is LiveRuntimeActivationDecision.ACTIVATION_READY
    assert report.runtime_activation_ready is True
    assert "No runtime integration" in report.message

@pytest.mark.parametrize("decision,ready", [
    (LiveRuntimeActivationDecision.ACTIVATION_READY, False),
    (LiveRuntimeActivationDecision.BLOCKED, True),
])
def test_report_rejects_inconsistent_decision(decision, ready):
    with pytest.raises(ValueError):
        LiveRuntimeActivationReport(NOW, decision, ready, "invalid")

def test_report_requires_timezone_aware_timestamp():
    with pytest.raises(ValueError):
        LiveRuntimeActivationReport(
            datetime(2026,10,10,2,0), LiveRuntimeActivationDecision.BLOCKED, False, "invalid")

def test_report_requires_nonempty_message():
    with pytest.raises(ValueError):
        LiveRuntimeActivationReport(NOW, LiveRuntimeActivationDecision.BLOCKED, False, " ")

def test_phase6f_step2_keeps_all_three_hard_locks_closed():
    assert LOCKED_LIVE_RUNTIME_INTEGRATION_ENABLED is False
    assert LIVE_BROKER_TRANSPORT_ENABLED is False
    assert LIVE_ORDER_TRANSMISSION_ENABLED is False

def test_runtime_activation_boundary_exposes_no_execution_side_effect_api():
    forbidden = {"unlock","arm","release","recover","start","run","process","execute",
                 "create","build","send","send_order","sendorder","submit","submit_order","transmit"}
    assert forbidden.isdisjoint(dir(LiveRuntimeActivationBoundary))
