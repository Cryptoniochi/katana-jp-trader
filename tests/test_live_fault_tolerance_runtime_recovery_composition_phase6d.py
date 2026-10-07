from pathlib import Path

from app.live.live_fault_tolerance_owner_lifecycle import FaultToleranceOwnerLifecycleState
from app.live.live_fault_tolerance_recovery_manager_factory import ProductionRecoveryManagerDependencies
from app.live.live_fault_tolerance_runtime_recovery_composition import ProductionFaultToleranceRuntimeRecoveryFactory
from app.supervisor.fault_tolerance_service import FaultToleranceService


class Sentinel:
    pass


class Exploding:
    def __getattr__(self, name):
        raise AssertionError(f"dependency was invoked: {name}")


def build_recovery_dependencies(factory=Sentinel):
    return ProductionRecoveryManagerDependencies(
        broker=factory(),
        health_service=factory(),
        order_repository=factory(),
        execution_service=factory(),
        portfolio_service=factory(),
        portfolio_audit_service=factory(),
        portfolio_repository=factory(),
    )


def test_factory_composes_complete_graph_without_starting_it():
    supervisor = Sentinel()
    persistence_boundary = Sentinel()
    deps = build_recovery_dependencies()
    bundle = ProductionFaultToleranceRuntimeRecoveryFactory.create(
        supervisor=supervisor,
        recovery_dependencies=deps,
        persistence_boundary=persistence_boundary,
    )
    assert bundle.runtime.lifecycle is bundle.lifecycle
    assert bundle.lifecycle.owner is bundle.owner
    assert bundle.owner.supervisor is supervisor
    assert bundle.owner.execution_boundary is bundle.execution_boundary
    assert bundle.execution_boundary.persistence_boundary is persistence_boundary
    assert isinstance(bundle.execution_boundary.service, FaultToleranceService)
    assert bundle.lifecycle.state is FaultToleranceOwnerLifecycleState.STOPPED
    assert bundle.runtime.is_running is False


def test_factory_preserves_exact_recovery_dependency_identity():
    deps = build_recovery_dependencies()
    bundle = ProductionFaultToleranceRuntimeRecoveryFactory.create(
        supervisor=Sentinel(),
        recovery_dependencies=deps,
        persistence_boundary=Sentinel(),
    )
    manager = bundle.execution_boundary.service.recovery_manager
    assert manager.broker is deps.broker
    assert manager.health_service is deps.health_service
    assert manager.order_repository is deps.order_repository
    assert manager.execution_service is deps.execution_service
    assert manager.portfolio_service is deps.portfolio_service
    assert manager.portfolio_audit_service is deps.portfolio_audit_service
    assert manager.portfolio_repository is deps.portfolio_repository


def test_factory_construction_invokes_no_operational_dependency_methods():
    bundle = ProductionFaultToleranceRuntimeRecoveryFactory.create(
        supervisor=Exploding(),
        recovery_dependencies=build_recovery_dependencies(Exploding),
        persistence_boundary=Exploding(),
    )
    assert bundle.runtime.is_running is False


def test_composition_source_contains_no_execution_calls():
    source = Path("app/live/live_fault_tolerance_runtime_recovery_composition.py").read_text(encoding="utf-8")
    forbidden = (
        ".recover(", ".run_once(", ".execute_once(", ".start(", ".heartbeat(",
        ".record_heartbeat(", ".stop(", ".persist(", ".require_ready(",
        ".reconcile_many(", ".create_snapshot(", ".audit(", ".save(",
        "sendorder", "send_order",
    )
    assert all(token not in source for token in forbidden)


def test_composition_does_not_choose_concrete_operational_dependencies():
    source = Path("app/live/live_fault_tolerance_runtime_recovery_composition.py").read_text(encoding="utf-8")
    forbidden = (
        "KabuStationClient(", "BrokerAdapter(", "OrderRepository(",
        "TradeExecutionRepository(", "PositionRepository(", "PortfolioRepository(",
        "LiveExecutionReconciliationService(", "PortfolioService(",
        "PortfolioAuditService(", "RecoveryManager(",
    )
    assert all(token not in source for token in forbidden)


def test_composition_not_wired_into_existing_runtime_paths():
    targets = (
        Path("app/runtime/paper_trading_composition.py"),
        Path("app/live/live_fault_tolerance_operator_boundary.py"),
        Path("app/live/live_fault_tolerance_runtime_composition.py"),
        Path("app/run_live_dry_run_operator.py"),
    )
    token = "ProductionFaultToleranceRuntimeRecoveryFactory"
    for target in targets:
        assert token not in target.read_text(encoding="utf-8")


def test_composition_has_no_scheduler_network_or_live_unlock_path():
    source = Path("app/live/live_fault_tolerance_runtime_recovery_composition.py").read_text(encoding="utf-8").lower()
    forbidden = (
        "requests.", "httpx.", "urllib.", "threading", "asyncio", "while true",
        "while 1", "schedule.", "timer(", "sleep(", "manual_kill_switch",
        ".release(", "live_order_transmission_enabled = true",
        "live_broker_transport_enabled = true",
        "locked_live_runtime_integration_enabled = true",
    )
    assert all(token not in source for token in forbidden)
