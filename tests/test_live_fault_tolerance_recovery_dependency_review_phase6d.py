from pathlib import Path

from app.live.live_fault_tolerance_recovery_dependency_review import (
    RecoveryDependencyDisposition,
    build_production_recovery_dependency_review,
)


EXPECTED_NAMES = (
    "broker",
    "health_service",
    "order_repository",
    "execution_service",
    "portfolio_service",
    "portfolio_audit_service",
    "portfolio_repository",
)


def test_review_covers_exact_recovery_manager_dependency_surface():
    review = build_production_recovery_dependency_review()
    assert tuple(item.name for item in review.items) == EXPECTED_NAMES


def test_broker_facing_dependencies_are_inject_only():
    review = build_production_recovery_dependency_review()
    dispositions = {item.name: item.disposition for item in review.items}
    for name in (
        "broker",
        "health_service",
        "execution_service",
        "portfolio_service",
        "portfolio_audit_service",
    ):
        assert dispositions[name] is RecoveryDependencyDisposition.INJECT_ONLY


def test_existing_sqlite_repository_contracts_are_marked_reusable():
    review = build_production_recovery_dependency_review()
    dispositions = {item.name: item.disposition for item in review.items}
    assert (
        dispositions["order_repository"]
        is RecoveryDependencyDisposition.REUSE_EXISTING
    )
    assert (
        dispositions["portfolio_repository"]
        is RecoveryDependencyDisposition.REUSE_EXISTING
    )


def test_review_is_explicitly_injection_oriented():
    review = build_production_recovery_dependency_review()
    assert review.all_require_explicit_injection is True
    assert all(item.rationale.strip() for item in review.items)


def test_step6cm_does_not_construct_operational_components():
    source = Path(
        "app/live/live_fault_tolerance_recovery_dependency_review.py"
    ).read_text(encoding="utf-8")
    forbidden = (
        "RecoveryManager(",
        "KabuStationClient(",
        "BrokerAdapter(",
        "LiveExecutionReconciliationService(",
        "PortfolioService(",
        "PortfolioAuditService(",
        "OrderRepository(",
        "PortfolioRepository(",
        "requests.",
        "httpx.",
        "urllib.",
        "sendorder",
        "send_order",
    )
    assert all(token not in source for token in forbidden)


def test_step6cm_not_wired_into_runtime_operator_paper_or_service_factory():
    targets = (
        Path("app/live/live_fault_tolerance_operator_boundary.py"),
        Path("app/live/live_fault_tolerance_runtime.py"),
        Path("app/live/live_fault_tolerance_production_composition.py"),
        Path("app/runtime/paper_trading_composition.py"),
        Path("app/run_live_dry_run_operator.py"),
    )
    token = "build_production_recovery_dependency_review"
    for target in targets:
        assert token not in target.read_text(encoding="utf-8")


def test_step6cm_has_no_scheduler_live_unlock_or_manual_kill_switch_mutation():
    source = Path(
        "app/live/live_fault_tolerance_recovery_dependency_review.py"
    ).read_text(encoding="utf-8").lower()
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
    assert all(token not in source for token in forbidden)
