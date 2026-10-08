"""Tests for Phase 6-F Step 1 Live activation transition contract."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.live.live_activation_authorization import (
    LiveActivationAuthorizationReport,
    LiveActivationAuthorizationState,
)
from app.live.live_activation_transition import (
    LiveActivationTransition,
    LiveActivationTransitionReport,
    LiveActivationTransitionState,
)
from app.live.live_broker_transport import LIVE_BROKER_TRANSPORT_ENABLED
from app.live.live_order_adapter import LIVE_ORDER_TRANSMISSION_ENABLED
from app.live.locked_live_runtime_integration import (
    LOCKED_LIVE_RUNTIME_INTEGRATION_ENABLED,
)


NOW = datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc)


def _authorization_report(*, ready: bool) -> LiveActivationAuthorizationReport:
    return LiveActivationAuthorizationReport(
        generated_at=NOW,
        authorization_ready=ready,
        state=(
            LiveActivationAuthorizationState.AUTHORIZATION_READY
            if ready
            else LiveActivationAuthorizationState.BLOCKED
        ),
        items=(),
    )


def test_blocked_authorization_keeps_every_transition_locked():
    report = LiveActivationTransition.evaluate(
        authorization_report=_authorization_report(ready=False),
        runtime_prerequisites_ready=True,
        transport_prerequisites_ready=True,
        order_transmission_prerequisites_ready=True,
    )

    assert report.state is LiveActivationTransitionState.LOCKED
    assert report.authorization_ready is False
    assert report.runtime_activation_ready is False
    assert report.transport_activation_ready is False
    assert report.order_transmission_activation_ready is False


def test_authorization_ready_does_not_imply_runtime_activation_ready():
    report = LiveActivationTransition.evaluate(
        authorization_report=_authorization_report(ready=True),
    )

    assert report.state is LiveActivationTransitionState.AUTHORIZATION_READY
    assert report.runtime_activation_ready is False
    assert report.transport_activation_ready is False
    assert report.order_transmission_activation_ready is False


def test_runtime_stage_requires_authorization_first():
    report = LiveActivationTransition.evaluate(
        authorization_report=_authorization_report(ready=True),
        runtime_prerequisites_ready=True,
    )

    assert report.state is LiveActivationTransitionState.RUNTIME_ACTIVATION_READY
    assert report.runtime_activation_ready is True
    assert report.transport_activation_ready is False
    assert report.order_transmission_activation_ready is False


def test_transport_stage_requires_runtime_stage():
    report = LiveActivationTransition.evaluate(
        authorization_report=_authorization_report(ready=True),
        runtime_prerequisites_ready=False,
        transport_prerequisites_ready=True,
    )

    assert report.state is LiveActivationTransitionState.AUTHORIZATION_READY
    assert report.transport_activation_ready is False


def test_order_stage_requires_transport_stage():
    report = LiveActivationTransition.evaluate(
        authorization_report=_authorization_report(ready=True),
        runtime_prerequisites_ready=True,
        transport_prerequisites_ready=False,
        order_transmission_prerequisites_ready=True,
    )

    assert report.state is LiveActivationTransitionState.RUNTIME_ACTIVATION_READY
    assert report.order_transmission_activation_ready is False


def test_all_modeled_prerequisites_can_reach_final_readiness_only():
    report = LiveActivationTransition.evaluate(
        authorization_report=_authorization_report(ready=True),
        runtime_prerequisites_ready=True,
        transport_prerequisites_ready=True,
        order_transmission_prerequisites_ready=True,
    )

    assert (
        report.state
        is LiveActivationTransitionState.ORDER_TRANSMISSION_ACTIVATION_READY
    )
    assert report.order_transmission_activation_ready is True
    assert "No Live execution lock has been changed." in report.message


def test_transition_report_rejects_transport_before_runtime():
    with pytest.raises(ValueError):
        LiveActivationTransitionReport(
            generated_at=NOW,
            state=LiveActivationTransitionState.TRANSPORT_ACTIVATION_READY,
            authorization_ready=True,
            runtime_activation_ready=False,
            transport_activation_ready=True,
            order_transmission_activation_ready=False,
            message="invalid",
        )


def test_transition_report_rejects_order_before_transport():
    with pytest.raises(ValueError):
        LiveActivationTransitionReport(
            generated_at=NOW,
            state=(
                LiveActivationTransitionState.ORDER_TRANSMISSION_ACTIVATION_READY
            ),
            authorization_ready=True,
            runtime_activation_ready=True,
            transport_activation_ready=False,
            order_transmission_activation_ready=True,
            message="invalid",
        )


def test_phase6f_step1_does_not_change_any_hard_live_lock():
    assert LOCKED_LIVE_RUNTIME_INTEGRATION_ENABLED is False
    assert LIVE_BROKER_TRANSPORT_ENABLED is False
    assert LIVE_ORDER_TRANSMISSION_ENABLED is False


def test_transition_contract_exposes_no_activation_side_effect_api():
    forbidden = {
        "unlock",
        "arm",
        "release",
        "recover",
        "start",
        "run",
        "execute",
        "send",
        "send_order",
        "sendorder",
        "submit",
        "submit_order",
        "transmit",
    }

    assert forbidden.isdisjoint(dir(LiveActivationTransition))
