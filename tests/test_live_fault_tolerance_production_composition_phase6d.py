from pathlib import Path

from app.live.live_fault_tolerance_production_composition import (
    ProductionFaultToleranceServiceFactory,
)
from app.live.live_fault_tolerance_production_dependencies import (
    ProductionFaultToleranceDependencies,
)
from app.live.recovery_models import RecoveryResult
from app.supervisor.fault_tolerance_models import FaultTolerancePolicy
from app.supervisor.fault_tolerance_service import FaultToleranceService


class SpySupervisor:
    def __init__(self):
        self.calls = 0

    def check(self):
        self.calls += 1
        raise AssertionError("construction must not evaluate supervisor")


class SpyRecovery:
    def __init__(self):
        self.calls = 0

    def recover(self, *, continue_on_error=False) -> RecoveryResult:
        self.calls += 1
        raise AssertionError("construction must not run recovery")


def test_dependency_bundle_is_inert():
    recovery = SpyRecovery()
    deps = ProductionFaultToleranceDependencies(recovery=recovery)
    assert deps.recovery is recovery
    assert recovery.calls == 0


def test_service_factory_is_inert_and_injects_exact_recovery():
    supervisor = SpySupervisor()
    recovery = SpyRecovery()
    deps = ProductionFaultToleranceDependencies(recovery=recovery)
    policy = FaultTolerancePolicy()

    service = ProductionFaultToleranceServiceFactory.create(
        supervisor=supervisor,
        dependencies=deps,
        policy=policy,
    )

    assert isinstance(service, FaultToleranceService)
    assert service.supervisor is supervisor
    assert service.recovery_manager is recovery
    assert service.policy is policy
    assert supervisor.calls == 0
    assert recovery.calls == 0


def test_factory_does_not_choose_recovery_implementation():
    source = Path(
        "app/live/live_fault_tolerance_production_composition.py"
    ).read_text(encoding="utf-8")
    assert "RecoveryManager(" not in source
    assert "KabuStation" not in source
    assert "BrokerAdapter" not in source
    assert "LiveExecutionReconciliationService(" not in source
    assert "PortfolioService(" not in source
    assert "PortfolioAuditService(" not in source
    assert "OrderRepository(" not in source
    assert "PortfolioRepository(" not in source


def test_dependency_contract_has_no_operational_construction():
    source = Path(
        "app/live/live_fault_tolerance_production_dependencies.py"
    ).read_text(encoding="utf-8")
    forbidden = (
        "RecoveryManager(",
        "KabuStation",
        "BrokerAdapter",
        "requests.",
        "httpx.",
        "urllib.",
        "sendorder",
        "send_order",
    )
    assert all(token not in source for token in forbidden)


def test_step6cl_not_wired_into_operator_runtime_paper_or_dry_run():
    targets = (
        Path("app/live/live_fault_tolerance_operator_boundary.py"),
        Path("app/live/live_fault_tolerance_runtime.py"),
        Path("app/runtime/paper_trading_composition.py"),
        Path("app/run_live_dry_run_operator.py"),
    )
    forbidden = (
        "ProductionFaultToleranceServiceFactory",
        "ProductionFaultToleranceDependencies",
    )
    for target in targets:
        source = target.read_text(encoding="utf-8")
        assert all(token not in source for token in forbidden)


def test_step6cl_has_no_scheduler_live_unlock_or_manual_release():
    targets = (
        Path("app/live/live_fault_tolerance_production_dependencies.py"),
        Path("app/live/live_fault_tolerance_production_composition.py"),
    )
    forbidden = (
        "threading",
        "asyncio",
        "while true",
        "while 1",
        "schedule.",
        "timer(",
        "sleep(",
        "manual_kill_switch",
        ".release(",
        "live_order_transmission_enabled = true",
        "live_broker_transport_enabled = true",
        "locked_live_runtime_integration_enabled = true",
    )
    for target in targets:
        source = target.read_text(encoding="utf-8").lower()
        assert all(token not in source for token in forbidden)
