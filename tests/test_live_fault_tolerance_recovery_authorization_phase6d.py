from dataclasses import dataclass
from pathlib import Path

from app.live.live_fault_tolerance_recovery_authorization import (
    ProductionFaultToleranceRecoveryAuthorization,
    ProductionFaultToleranceRecoveryAuthorizationProviders,
)
from app.live.live_fault_tolerance_recovery_authorization_composition import (
    ProductionFaultToleranceRecoveryAuthorizationFactory,
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


def test_all_reviewed_inputs_authorize():
    authorization = ProductionFaultToleranceRecoveryAuthorization(
        providers=providers()
    )
    snapshot = authorization.evaluate()
    assert snapshot.authorized is True
    assert authorization() is True


def test_each_false_input_blocks_fail_closed():
    names = (
        "manual_kill_switch_released",
        "runtime_healthy",
        "heartbeat_alive",
        "broker_available",
        "reconciliation_consistent",
    )
    for name in names:
        authorization = ProductionFaultToleranceRecoveryAuthorization(
            providers=providers(**{name: lambda: False})
        )
        snapshot = authorization.evaluate()
        assert snapshot.authorized is False
        assert getattr(snapshot, name) is False


def test_truthy_non_bool_is_not_safe():
    authorization = ProductionFaultToleranceRecoveryAuthorization(
        providers=providers(broker_available=lambda: 1)
    )
    assert authorization.evaluate().authorized is False


def test_provider_exception_blocks_and_records_reason():
    def explode():
        raise RuntimeError("stale state")

    authorization = ProductionFaultToleranceRecoveryAuthorization(
        providers=providers(runtime_healthy=explode)
    )
    snapshot = authorization.evaluate()
    assert snapshot.authorized is False
    assert "failed closed" in snapshot.reason
    assert "RuntimeError" in snapshot.reason


def test_short_circuits_after_first_unsafe_provider():
    calls = {"later": 0}

    def later():
        calls["later"] += 1
        return True

    authorization = ProductionFaultToleranceRecoveryAuthorization(
        providers=providers(
            manual_kill_switch_released=lambda: False,
            runtime_healthy=later,
        )
    )
    assert authorization.evaluate().authorized is False
    assert calls["later"] == 0


@dataclass
class RuntimeStub:
    calls: int = 0
    result: object = None

    def run_once(self):
        self.calls += 1
        return self.result


def test_factory_connects_authorization_to_gate_without_executing():
    calls = {"provider": 0}

    def provider():
        calls["provider"] += 1
        return True

    runtime = RuntimeStub(result=object())
    bundle = ProductionFaultToleranceRecoveryAuthorizationFactory.create(
        runtime=runtime,
        providers=providers(runtime_healthy=provider),
    )
    assert calls["provider"] == 0
    assert runtime.calls == 0
    result = bundle.gate.run_once()
    assert result.allowed is True
    assert runtime.calls == 1
    assert calls["provider"] == 1


def test_blocked_authorization_never_calls_runtime():
    runtime = RuntimeStub()
    bundle = ProductionFaultToleranceRecoveryAuthorizationFactory.create(
        runtime=runtime,
        providers=providers(reconciliation_consistent=lambda: False),
    )
    result = bundle.gate.run_once()
    assert result.allowed is False
    assert runtime.calls == 0


def test_authorization_is_not_wired_into_existing_operational_paths():
    tokens = (
        "ProductionFaultToleranceRecoveryAuthorizationFactory",
        "ProductionFaultToleranceRecoveryAuthorizationProviders",
    )
    targets = (
        Path("app/runtime/paper_trading_composition.py"),
        Path("app/live/live_fault_tolerance_runtime.py"),
        Path("app/live/live_fault_tolerance_runtime_recovery_composition.py"),
        Path("app/run_live_dry_run_operator.py"),
    )
    for target in targets:
        source = target.read_text(encoding="utf-8")
        assert all(token not in source for token in tokens)


def test_authorization_has_no_network_scheduler_recovery_or_live_unlock():
    source = Path(
        "app/live/live_fault_tolerance_recovery_authorization.py"
    ).read_text(encoding="utf-8").lower()
    forbidden = (
        ".recover(",
        ".run_once(",
        ".execute_once(",
        ".start(",
        ".stop(",
        ".persist(",
        "requests.",
        "httpx.",
        "urllib.",
        "threading",
        "asyncio",
        "while true",
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
