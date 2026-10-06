from pathlib import Path

from app.live.live_fault_tolerance_recovery_manager_factory import (
    ProductionRecoveryManagerDependencies,
    ProductionRecoveryManagerFactory,
)
from app.live.recovery_manager import RecoveryManager


class Sentinel:
    pass


def build_dependencies():
    return ProductionRecoveryManagerDependencies(
        broker=Sentinel(),
        health_service=Sentinel(),
        order_repository=Sentinel(),
        execution_service=Sentinel(),
        portfolio_service=Sentinel(),
        portfolio_audit_service=Sentinel(),
        portfolio_repository=Sentinel(),
    )


def test_dependency_bundle_is_inert_and_preserves_identity():
    deps = build_dependencies()
    assert isinstance(deps.broker, Sentinel)
    assert isinstance(deps.health_service, Sentinel)
    assert isinstance(deps.order_repository, Sentinel)
    assert isinstance(deps.execution_service, Sentinel)
    assert isinstance(deps.portfolio_service, Sentinel)
    assert isinstance(deps.portfolio_audit_service, Sentinel)
    assert isinstance(deps.portfolio_repository, Sentinel)


def test_factory_constructs_recovery_manager_with_exact_dependencies():
    deps = build_dependencies()
    manager = ProductionRecoveryManagerFactory.create(dependencies=deps)

    assert isinstance(manager, RecoveryManager)
    assert manager.broker is deps.broker
    assert manager.health_service is deps.health_service
    assert manager.order_repository is deps.order_repository
    assert manager.execution_service is deps.execution_service
    assert manager.portfolio_service is deps.portfolio_service
    assert manager.portfolio_audit_service is deps.portfolio_audit_service
    assert manager.portfolio_repository is deps.portfolio_repository


def test_factory_does_not_invoke_recovery_or_dependency_methods():
    class Exploding:
        def __getattr__(self, name):
            raise AssertionError(f"dependency was invoked: {name}")

    deps = ProductionRecoveryManagerDependencies(
        broker=Exploding(),
        health_service=Exploding(),
        order_repository=Exploding(),
        execution_service=Exploding(),
        portfolio_service=Exploding(),
        portfolio_audit_service=Exploding(),
        portfolio_repository=Exploding(),
    )
    manager = ProductionRecoveryManagerFactory.create(dependencies=deps)
    assert isinstance(manager, RecoveryManager)


def test_factory_does_not_choose_concrete_operational_implementations():
    source = Path(
        "app/live/live_fault_tolerance_recovery_manager_factory.py"
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
        ".recover(",
        ".require_ready(",
        ".reconcile_many(",
        ".create_snapshot(",
        ".audit(",
        ".save(",
        "sendorder",
        "send_order",
    )
    assert all(token not in source for token in forbidden)


def test_factory_not_wired_into_fault_tolerance_service_composition():
    source = Path(
        "app/live/live_fault_tolerance_production_composition.py"
    ).read_text(encoding="utf-8")
    assert "ProductionRecoveryManagerFactory" not in source


def test_factory_not_wired_into_operator_runtime_paper_or_dry_run():
    targets = (
        Path("app/live/live_fault_tolerance_operator_boundary.py"),
        Path("app/live/live_fault_tolerance_runtime.py"),
        Path("app/runtime/paper_trading_composition.py"),
        Path("app/run_live_dry_run_operator.py"),
    )
    token = "ProductionRecoveryManagerFactory"
    for target in targets:
        assert token not in target.read_text(encoding="utf-8")


def test_factory_has_no_scheduler_network_or_live_unlock_path():
    source = Path(
        "app/live/live_fault_tolerance_recovery_manager_factory.py"
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
