from datetime import datetime, timezone
from pathlib import Path

from app.live.live_activation_authorization import (
    LiveActivationAuthorizationGate,
    LiveActivationAuthorizationProviders,
    LiveActivationAuthorizationState,
)
from app.live.live_broker_transport import LIVE_BROKER_TRANSPORT_ENABLED
from app.live.live_order_adapter import LIVE_ORDER_TRANSMISSION_ENABLED
from app.live.locked_live_runtime_integration import (
    LOCKED_LIVE_RUNTIME_INTEGRATION_ENABLED,
)

NOW = datetime(2026, 10, 7, 9, 0, tzinfo=timezone.utc)


def providers(**overrides):
    values = {
        "final_readiness_activation_ready": lambda: True,
        "manual_kill_switch_released": lambda: True,
        "runtime_healthy": lambda: True,
        "heartbeat_alive": lambda: True,
        "broker_available": lambda: True,
        "reconciliation_consistent": lambda: True,
    }
    values.update(overrides)
    return LiveActivationAuthorizationProviders(**values)


def gate(**overrides):
    return LiveActivationAuthorizationGate(
        providers=providers(**overrides),
        now_provider=lambda: NOW,
    )


def test_all_reviewed_prerequisites_can_be_authorization_ready():
    report = gate().check()
    assert report.authorization_ready is True
    assert report.state is LiveActivationAuthorizationState.AUTHORIZATION_READY
    assert all(item.passed for item in report.items)


def test_final_readiness_false_blocks():
    report = gate(final_readiness_activation_ready=lambda: False).check()
    assert report.authorization_ready is False


def test_manual_kill_switch_not_released_blocks():
    assert gate(manual_kill_switch_released=lambda: False).check().authorization_ready is False


def test_runtime_unhealthy_blocks():
    assert gate(runtime_healthy=lambda: False).check().authorization_ready is False


def test_dead_heartbeat_blocks():
    assert gate(heartbeat_alive=lambda: False).check().authorization_ready is False


def test_broker_unavailable_blocks():
    assert gate(broker_available=lambda: False).check().authorization_ready is False


def test_reconciliation_inconsistent_blocks():
    assert gate(reconciliation_consistent=lambda: False).check().authorization_ready is False


def test_provider_exception_fails_closed():
    def explode():
        raise RuntimeError("unavailable")
    report = gate(broker_available=explode).check()
    assert report.authorization_ready is False
    item = next(item for item in report.items if item.key == "broker_availability")
    assert item.passed is False
    assert "RuntimeError" in item.message


def test_literal_true_is_required():
    assert gate(runtime_healthy=lambda: 1).check().authorization_ready is False


def test_all_live_hard_locks_remain_false():
    assert LIVE_ORDER_TRANSMISSION_ENABLED is False
    assert LIVE_BROKER_TRANSPORT_ENABLED is False
    assert LOCKED_LIVE_RUNTIME_INTEGRATION_ENABLED is False


def test_authorization_ready_does_not_unlock_any_hard_lock():
    assert gate().check().authorization_ready is True
    assert LIVE_ORDER_TRANSMISSION_ENABLED is False
    assert LIVE_BROKER_TRANSPORT_ENABLED is False
    assert LOCKED_LIVE_RUNTIME_INTEGRATION_ENABLED is False


def test_module_contains_no_unlock_network_or_order_submission():
    source = Path("app/live/live_activation_authorization.py").read_text(
        encoding="utf-8"
    ).lower()
    forbidden = (
        "sendorder", "send_order(", "submit_order(", "requests.", "httpx.",
        "urllib.", ".release(", ".recover(", ".run_once(", "enabled = true",
        "runtime_armed=true", "runtime_armed = true",
    )
    assert all(token not in source for token in forbidden)
