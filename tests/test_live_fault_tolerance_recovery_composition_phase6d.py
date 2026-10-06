from datetime import datetime, timezone
from pathlib import Path

from app.live.live_fault_tolerance_recovery_composition import (
    ProductionFaultToleranceRecoveryComposition,
)
from app.live.live_fault_tolerance_recovery_manager_factory import (
    ProductionRecoveryManagerDependencies,
)
from app.live.recovery_manager import RecoveryManager
from app.supervisor.fault_tolerance_models import FaultTolerancePolicy
from app.supervisor.fault_tolerance_service import FaultToleranceService


class Sentinel:
    pass


class SupervisorSentinel:
    pass


def build_recovery_dependencies():
    return ProductionRecoveryManagerDependencies(
        broker=Sentinel(),
        health_service=Sentinel(),
        order_repository=Sentinel(),
        execution_service=Sentinel(),
        portfolio_service=Sentinel(),
        portfolio_audit_service=Sentinel(),
        portfolio_repository=Sentinel(),
    )


def test_composition_constructs_service_and_recovery_manager():
    supervisor = SupervisorSentinel()
    deps = build_recovery_dependencies()

    service = ProductionFaultToleranceRecoveryComposition.create(
        supervisor=supervisor,
        recovery_dependencies=deps,
    )

    assert isinstance(service, FaultToleranceService)
    assert service.supervisor is supervisor
    assert isinstance(service.recovery_manager, RecoveryManager)


def test_composition_preserves_exact_recovery_dependency_identity():
    deps = build_recovery_dependencies()
    service = ProductionFaultToleranceRecoveryComposition.create(
        supervisor=SupervisorSentinel(),
        recovery_dependencies=deps,
    )
    manager = service.recovery_manager

    assert manager.broker is deps.broker
    assert manager.health_service is deps.health_service
    assert manager.order_repository is deps.order_repository
    assert manager.execution_service is deps.execution_service
    assert manager.portfolio_service is deps.portfolio_service
    assert manager.portfolio_audit_service is deps.portfolio_audit_service
    assert manager.portfolio_repository is deps.portfolio_repository


def test_composition_preserves_policy_and_clock():
    policy = FaultTolerancePolicy(
        maximum_consecutive_recovery_failures=2,
        continue_recovery_on_error=False,
    )
    now = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)

    service = ProductionFaultToleranceRecoveryComposition.create(
        supervisor=SupervisorSentinel(),
        recovery_dependencies=build_recovery_dependencies(),
        policy=policy,
        now_provider=lambda: now,
    )

    assert service.policy is policy
    assert service.now_provider() == now


def test_construction_does_not_invoke_supervisor_or_recovery_dependencies():
    class Exploding:
        def __getattr__(self, name):
            raise AssertionError(f"operational dependency invoked: {name}")

    deps = ProductionRecoveryManagerDependencies(
        broker=Exploding(),
        health_service=Exploding(),
        order_repository=Exploding(),
        execution_service=Exploding(),
        portfolio_service=Exploding(),
        portfolio_audit_service=Exploding(),
        portfolio_repository=Exploding(),
    )

    service = ProductionFaultToleranceRecoveryComposition.create(
        supervisor=Exploding(),
        recovery_dependencies=deps,
    )
    assert isinstance(service, FaultToleranceService)


def test_composition_source_has_no_operational_execution_calls():
    source = Path(
        "app/live/live_fault_tolerance_recovery_composition.py"
    ).read_text(encoding="utf-8")

    executable_source = source
    if executable_source.startswith('"""'):
        _, _, remainder = executable_source.partition('"""')
        _, _, executable_source = remainder.partition('"""')

    forbidden = (
        ".run_once(",
        ".recover(",
        ".check(",
        ".restart_decision(",
        ".mark_restarted(",
        ".stop(",
        ".require_ready(",
        ".reconcile_many(",
        ".create_snapshot(",
        ".audit(",
        ".save(",
        "sendorder",
        "send_order",
    )
    assert all(token not in executable_source for token in forbidden)


def test_composition_does_not_construct_concrete_operational_dependencies():
    source = Path(
        "app/live/live_fault_tolerance_recovery_composition.py"
    ).read_text(encoding="utf-8")

    forbidden = (
        "KabuStationClient(",
        "BrokerAdapter(",
        "OrderRepository(",
        "TradeExecutionRepository(",
        "PositionRepository(",
        "PortfolioRepository(",
        "LiveExecutionReconciliationService(",
        "PortfolioService(",
        "PortfolioAuditService(",
    )
    assert all(token not in source for token in forbidden)


def test_composition_not_wired_into_operator_runtime_paper_or_dry_run():
    targets = (
        Path("app/live/live_fault_tolerance_operator_boundary.py"),
        Path("app/live/live_fault_tolerance_runtime.py"),
        Path("app/runtime/paper_trading_composition.py"),
        Path("app/run_live_dry_run_operator.py"),
    )
    token = "ProductionFaultToleranceRecoveryComposition"
    for target in targets:
        assert token not in target.read_text(encoding="utf-8")


def test_composition_has_no_scheduler_network_or_live_unlock_path():
    source = Path(
        "app/live/live_fault_tolerance_recovery_composition.py"
    ).read_text(encoding="utf-8").lower()

    forbidden = (
        "requests.",
        "httpx.",
        "urllib.",
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
    assert all(token not in source for token in forbidden)
