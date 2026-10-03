from datetime import date, datetime, timedelta, timezone

from app.live.live_order_safety import safety_snapshot_from_states
from app.live.three_way_reconciliation import (
    ReconciliationOrder,
    ThreeWayReconciliationService,
)
from app.supervisor.fault_tolerance_models import (
    FaultToleranceAttempt,
    FaultToleranceDecision,
)
from app.supervisor.supervisor_models import (
    SupervisorSnapshot,
    SupervisorStatus,
)


NOW = datetime(2026, 10, 3, 3, 0, 0, tzinfo=timezone.utc)
TRADING_DATE = date(2026, 10, 3)


def _order(*, quantity: int = 100) -> ReconciliationOrder:
    return ReconciliationOrder(
        order_id="order-1",
        signal_id="signal-1",
        code="7203",
        side="buy",
        quantity=quantity,
    )


def _reconciliation(
    *,
    paper_quantity: int = 100,
    shadow_quantity: int = 100,
    connected: bool = True,
    active_orders: tuple[str, ...] = (),
    positions: tuple[str, ...] = (),
):
    return ThreeWayReconciliationService().reconcile(
        trading_date=TRADING_DATE,
        paper_orders=(_order(quantity=paper_quantity),),
        shadow_orders=(_order(quantity=shadow_quantity),),
        broker_snapshot_connected=connected,
        broker_active_order_ids=active_orders,
        broker_position_codes=positions,
    )


def _supervisor_snapshot(
    *,
    checked_at: datetime = NOW,
) -> SupervisorSnapshot:
    return SupervisorSnapshot(
        worker_name="phase6c-step3d",
        status=SupervisorStatus.RUNNING,
        started_at=checked_at - timedelta(minutes=5),
        checked_at=checked_at,
        last_heartbeat_at=checked_at,
        last_restart_at=None,
        restart_count=0,
        stop_reason=None,
        message="running",
    )


def _fault_attempt(
    decision: FaultToleranceDecision,
    *,
    checked_at: datetime = NOW,
) -> FaultToleranceAttempt:
    supervisor = _supervisor_snapshot(checked_at=checked_at)
    return FaultToleranceAttempt(
        attempt_number=1,
        checked_at=checked_at,
        decision=decision,
        supervisor_before=supervisor,
        supervisor_after=supervisor,
        recovery_result=None,
        consecutive_failure_count=0,
        next_action_at=None,
        message=f"phase6c-step3d-{decision.value}",
    )


def test_real_consistent_reconciliation_without_fault_attempt_is_safe():
    report = _reconciliation()

    snapshot = safety_snapshot_from_states(
        reconciliation_report=report,
        fault_tolerance_attempt=None,
    )

    assert report.consistent is True
    assert report.state == "consistent"
    assert report.live_order_ready is False
    assert snapshot.safe_stop_active is False
    assert snapshot.reconciliation_consistent is True
    assert snapshot.reconciliation_state == "consistent"
    assert snapshot.is_blocked is False
    assert snapshot.evaluated_at == report.generated_at


def test_real_safe_stop_attempt_blocks_even_with_consistent_reconciliation():
    report = _reconciliation()
    attempt = _fault_attempt(
        FaultToleranceDecision.SAFE_STOP,
        checked_at=report.generated_at + timedelta(seconds=1),
    )

    snapshot = safety_snapshot_from_states(
        reconciliation_report=report,
        fault_tolerance_attempt=attempt,
    )

    assert report.consistent is True
    assert snapshot.safe_stop_active is True
    assert snapshot.reconciliation_consistent is True
    assert snapshot.is_blocked is True
    assert snapshot.evaluated_at == attempt.checked_at


def test_real_no_action_does_not_raise_safe_stop():
    report = _reconciliation()
    attempt = _fault_attempt(
        FaultToleranceDecision.NO_ACTION,
        checked_at=report.generated_at + timedelta(seconds=1),
    )

    snapshot = safety_snapshot_from_states(
        reconciliation_report=report,
        fault_tolerance_attempt=attempt,
    )

    assert snapshot.safe_stop_active is False
    assert snapshot.reconciliation_consistent is True
    assert snapshot.is_blocked is False


def test_real_recovery_failed_does_not_impersonate_safe_stop():
    report = _reconciliation()
    attempt = _fault_attempt(
        FaultToleranceDecision.RECOVERY_FAILED,
        checked_at=report.generated_at + timedelta(seconds=1),
    )

    snapshot = safety_snapshot_from_states(
        reconciliation_report=report,
        fault_tolerance_attempt=attempt,
    )

    assert snapshot.safe_stop_active is False
    assert snapshot.reconciliation_consistent is True
    assert snapshot.is_blocked is False


def test_real_quantity_mismatch_blocks_reconciliation_bridge():
    report = _reconciliation(
        paper_quantity=100,
        shadow_quantity=200,
    )

    snapshot = safety_snapshot_from_states(
        reconciliation_report=report,
        fault_tolerance_attempt=None,
    )

    assert report.consistent is False
    assert report.state == "blocked"
    assert snapshot.safe_stop_active is False
    assert snapshot.reconciliation_consistent is False
    assert snapshot.reconciliation_state == "blocked"
    assert snapshot.is_blocked is True


def test_real_broker_inventory_blocks_reconciliation_bridge():
    report = _reconciliation(
        active_orders=("broker-order-1",),
        positions=("7203",),
    )

    snapshot = safety_snapshot_from_states(
        reconciliation_report=report,
        fault_tolerance_attempt=None,
    )

    assert report.consistent is False
    assert report.state == "blocked"
    assert report.broker_active_order_count == 1
    assert report.broker_position_count == 1
    assert snapshot.reconciliation_consistent is False
    assert snapshot.is_blocked is True


def test_real_disconnected_broker_blocks_reconciliation_bridge():
    report = _reconciliation(connected=False)

    snapshot = safety_snapshot_from_states(
        reconciliation_report=report,
        fault_tolerance_attempt=None,
    )

    assert report.consistent is False
    assert report.state == "blocked"
    assert report.broker_snapshot_connected is False
    assert snapshot.reconciliation_consistent is False
    assert snapshot.is_blocked is True


def test_bridge_uses_newest_real_safety_timestamp():
    report = _reconciliation()
    attempt = _fault_attempt(
        FaultToleranceDecision.NO_ACTION,
        checked_at=report.generated_at + timedelta(seconds=5),
    )

    snapshot = safety_snapshot_from_states(
        reconciliation_report=report,
        fault_tolerance_attempt=attempt,
    )

    assert snapshot.evaluated_at == attempt.checked_at
