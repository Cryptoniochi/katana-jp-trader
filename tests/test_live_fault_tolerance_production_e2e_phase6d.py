from dataclasses import dataclass
from pathlib import Path

from app.live.live_fault_tolerance_authorized_operator_composition import (
    ProductionFaultToleranceAuthorizedOperatorFactory,
)
from app.live.live_fault_tolerance_production_read_only_authorization import (
    ProductionFaultToleranceReadOnlyAuthorizationFactory,
)
from app.live.locked_live_runtime_integration import (
    LOCKED_LIVE_RUNTIME_INTEGRATION_ENABLED,
)


@dataclass
class Reconciliation:
    consistent: bool


@dataclass
class ReadOnlyProviders:
    runtime_health_ok_provider: object
    heartbeat_alive_provider: object
    broker_available_provider: object
    reconciliation_report_provider: object
    manual_blocked_provider: object


@dataclass
class RuntimeStub:
    events: list
    running: bool = False
    execution_result: object = None

    def start(self):
        self.events.append("start")
        self.running = True
        return "start"

    def heartbeat(self):
        self.events.append("heartbeat")
        return "heartbeat"

    def run_once(self):
        self.events.append("recovery")
        return self.execution_result

    def stop(self, *, reason, message=None):
        self.events.append("stop")
        self.running = False
        return "stop"


def read_only(**overrides):
    values = {
        "runtime_health_ok_provider": lambda: True,
        "heartbeat_alive_provider": lambda: True,
        "broker_available_provider": lambda: True,
        "reconciliation_report_provider": lambda: Reconciliation(True),
        "manual_blocked_provider": lambda: False,
    }
    values.update(overrides)
    return ReadOnlyProviders(**values)


def compose(runtime, state):
    providers = ProductionFaultToleranceReadOnlyAuthorizationFactory.create(
        read_only_providers=state,
    )
    return ProductionFaultToleranceAuthorizedOperatorFactory.create(
        runtime=runtime,
        providers=providers,
    )


def test_production_read_only_adapter_construction_is_inert():
    calls = {"count": 0}

    def counted():
        calls["count"] += 1
        return True

    ProductionFaultToleranceReadOnlyAuthorizationFactory.create(
        read_only_providers=read_only(runtime_health_ok_provider=counted)
    )
    assert calls["count"] == 0


def test_manual_blocked_state_blocks_end_to_end_before_recovery():
    runtime = RuntimeStub(events=[])
    result = compose(
        runtime,
        read_only(manual_blocked_provider=lambda: True),
    ).operator.run_once()
    assert result.gate.allowed is False
    assert runtime.events == ["start", "heartbeat", "stop"]


def test_unhealthy_runtime_blocks_end_to_end_before_recovery():
    runtime = RuntimeStub(events=[])
    result = compose(
        runtime,
        read_only(runtime_health_ok_provider=lambda: False),
    ).operator.run_once()
    assert result.gate.allowed is False
    assert runtime.events == ["start", "heartbeat", "stop"]


def test_dead_heartbeat_blocks_end_to_end_before_recovery():
    runtime = RuntimeStub(events=[])
    result = compose(
        runtime,
        read_only(heartbeat_alive_provider=lambda: False),
    ).operator.run_once()
    assert result.gate.allowed is False
    assert runtime.events == ["start", "heartbeat", "stop"]


def test_unavailable_broker_blocks_end_to_end_before_recovery():
    runtime = RuntimeStub(events=[])
    result = compose(
        runtime,
        read_only(broker_available_provider=lambda: False),
    ).operator.run_once()
    assert result.gate.allowed is False
    assert runtime.events == ["start", "heartbeat", "stop"]


def test_missing_reconciliation_blocks_end_to_end_before_recovery():
    runtime = RuntimeStub(events=[])
    result = compose(
        runtime,
        read_only(reconciliation_report_provider=lambda: None),
    ).operator.run_once()
    assert result.gate.allowed is False
    assert runtime.events == ["start", "heartbeat", "stop"]


def test_inconsistent_reconciliation_blocks_end_to_end_before_recovery():
    runtime = RuntimeStub(events=[])
    result = compose(
        runtime,
        read_only(
            reconciliation_report_provider=lambda: Reconciliation(False)
        ),
    ).operator.run_once()
    assert result.gate.allowed is False
    assert runtime.events == ["start", "heartbeat", "stop"]


def test_provider_exception_fails_closed_end_to_end():
    def explode():
        raise RuntimeError("stale production state")

    runtime = RuntimeStub(events=[])
    result = compose(
        runtime,
        read_only(broker_available_provider=explode),
    ).operator.run_once()
    assert result.gate.allowed is False
    assert runtime.events == ["start", "heartbeat", "stop"]


def test_all_safe_read_only_inputs_allow_exactly_one_recovery_evaluation():
    runtime = RuntimeStub(events=[], execution_result=object())
    result = compose(runtime, read_only()).operator.run_once()
    assert result.gate.allowed is True
    assert result.gate.executed is True
    assert runtime.events == ["start", "heartbeat", "recovery", "stop"]
    assert runtime.running is False


def test_phase6d_live_runtime_integration_hard_lock_remains_false():
    assert LOCKED_LIVE_RUNTIME_INTEGRATION_ENABLED is False


def test_all_known_live_transport_hard_locks_remain_false_when_available():
    import app.live.live_broker_transport as transport_module
    assert transport_module.LIVE_BROKER_TRANSPORT_ENABLED is False

    candidates = (
        ("app.live.live_order_transmission", "LIVE_ORDER_TRANSMISSION_ENABLED"),
        ("app.live.live_order_transmission_gate", "LIVE_ORDER_TRANSMISSION_ENABLED"),
        ("app.live.locked_live_order_transmission", "LIVE_ORDER_TRANSMISSION_ENABLED"),
    )
    found = False
    for module_name, constant_name in candidates:
        try:
            module = __import__(module_name, fromlist=[constant_name])
        except ModuleNotFoundError:
            continue
        if hasattr(module, constant_name):
            found = True
            assert getattr(module, constant_name) is False
    if not found:
        # The locked transport plus disabled runtime integration are still
        # mandatory; absence of a separate transmission module is acceptable.
        assert LOCKED_LIVE_RUNTIME_INTEGRATION_ENABLED is False


def test_production_adapter_not_wired_into_paper_or_dry_run():
    token = "ProductionFaultToleranceReadOnlyAuthorizationFactory"
    targets = (
        Path("app/runtime/paper_trading_composition.py"),
        Path("app/run_live_dry_run_operator.py"),
        Path("app/live/locked_live_runtime_integration.py"),
    )
    for target in targets:
        assert token not in target.read_text(encoding="utf-8")


def test_production_adapter_contains_no_network_execution_or_unlock():
    source = Path(
        "app/live/live_fault_tolerance_production_read_only_authorization.py"
    ).read_text(encoding="utf-8").lower()
    forbidden = (
        ".run_once(",
        ".recover(",
        ".start(",
        ".stop(",
        ".persist(",
        "requests.",
        "httpx.",
        "urllib.",
        "sendorder",
        "send_order",
        ".release(",
        "enabled = true",
    )
    assert all(token not in source for token in forbidden)
