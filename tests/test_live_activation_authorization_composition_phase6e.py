from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from app.live.live_activation_authorization import (
    LiveActivationAuthorizationState,
)
from app.live.live_activation_authorization_composition import (
    ProductionLiveActivationAuthorizationFactory,
)
from app.live.live_broker_transport import LIVE_BROKER_TRANSPORT_ENABLED
from app.live.live_order_adapter import LIVE_ORDER_TRANSMISSION_ENABLED
from app.live.locked_live_runtime_integration import (
    LOCKED_LIVE_RUNTIME_INTEGRATION_ENABLED,
)


NOW = datetime(2026, 10, 7, 10, 0, tzinfo=timezone.utc)


@dataclass
class Calls:
    final: int = 0
    manual: int = 0
    runtime: int = 0
    heartbeat: int = 0
    broker: int = 0
    reconciliation: int = 0


def bundle(calls, *, manual_blocked=False, consistent=True):
    def manual():
        calls.manual += 1
        return manual_blocked

    def runtime():
        calls.runtime += 1
        return True

    def heartbeat():
        calls.heartbeat += 1
        return True

    def broker():
        calls.broker += 1
        return True

    def reconciliation():
        calls.reconciliation += 1
        return SimpleNamespace(consistent=consistent)

    return SimpleNamespace(
        manual_blocked_provider=manual,
        runtime_health_ok_provider=runtime,
        heartbeat_alive_provider=heartbeat,
        broker_available_provider=broker,
        reconciliation_report_provider=reconciliation,
    )


def final_provider(calls, value=True):
    def provider():
        calls.final += 1
        return value
    return provider


def create(calls, **kwargs):
    return ProductionLiveActivationAuthorizationFactory.create(
        read_only_providers=bundle(calls, **kwargs),
        final_readiness_activation_ready_provider=final_provider(calls),
        now_provider=lambda: NOW,
    )


def test_construction_is_inert_and_does_not_evaluate_providers():
    calls = Calls()
    gate = create(calls)
    assert gate is not None
    assert calls == Calls()


def test_all_read_only_inputs_safe_can_be_authorization_ready():
    calls = Calls()
    report = create(calls).check()
    assert report.authorization_ready is True
    assert report.state is LiveActivationAuthorizationState.AUTHORIZATION_READY
    assert calls == Calls(1, 1, 1, 1, 1, 1)


def test_manual_blocked_fails_closed():
    calls = Calls()
    report = create(calls, manual_blocked=True).check()
    assert report.authorization_ready is False


def test_missing_reconciliation_fails_closed():
    calls = Calls()
    providers = bundle(calls)
    providers.reconciliation_report_provider = lambda: None
    gate = ProductionLiveActivationAuthorizationFactory.create(
        read_only_providers=providers,
        final_readiness_activation_ready_provider=final_provider(calls),
        now_provider=lambda: NOW,
    )
    assert gate.check().authorization_ready is False


def test_non_literal_reconciliation_consistency_fails_closed():
    calls = Calls()
    providers = bundle(calls)
    providers.reconciliation_report_provider = (
        lambda: SimpleNamespace(consistent=1)
    )
    gate = ProductionLiveActivationAuthorizationFactory.create(
        read_only_providers=providers,
        final_readiness_activation_ready_provider=final_provider(calls),
        now_provider=lambda: NOW,
    )
    assert gate.check().authorization_ready is False


def test_final_readiness_false_blocks_even_when_read_only_inputs_are_safe():
    calls = Calls()
    gate = ProductionLiveActivationAuthorizationFactory.create(
        read_only_providers=bundle(calls),
        final_readiness_activation_ready_provider=final_provider(calls, False),
        now_provider=lambda: NOW,
    )
    assert gate.check().authorization_ready is False


def test_provider_exception_fails_closed():
    calls = Calls()
    providers = bundle(calls)

    def explode():
        raise RuntimeError("broker state unavailable")

    providers.broker_available_provider = explode
    gate = ProductionLiveActivationAuthorizationFactory.create(
        read_only_providers=providers,
        final_readiness_activation_ready_provider=final_provider(calls),
        now_provider=lambda: NOW,
    )
    assert gate.check().authorization_ready is False


def test_authorization_ready_keeps_all_hard_locks_closed():
    calls = Calls()
    assert create(calls).check().authorization_ready is True
    assert LIVE_ORDER_TRANSMISSION_ENABLED is False
    assert LIVE_BROKER_TRANSPORT_ENABLED is False
    assert LOCKED_LIVE_RUNTIME_INTEGRATION_ENABLED is False


def test_composition_contains_no_unlock_execution_or_network_path():
    source = Path(
        "app/live/live_activation_authorization_composition.py"
    ).read_text(encoding="utf-8").lower()
    forbidden = (
        "sendorder",
        "send_order(",
        "submit_order(",
        "requests.",
        "httpx.",
        "urllib.",
        ".release(",
        ".recover(",
        ".run_once(",
        ".process(",
        "runtime_armed",
        "enabled = true",
    )
    assert all(token not in source for token in forbidden)
