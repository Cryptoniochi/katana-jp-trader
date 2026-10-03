"""Phase 6-C Step 3A real-component live execution lifecycle tests.

These tests deliberately use the real Phase 6-A/6-B/6-C components rather
than a boundary-sequence stub.  No broker adapter or network transport is
introduced.
"""

from datetime import date, datetime, timezone

from app.live.execution_mode import (
    ExecutionModeSettings,
    TradingExecutionMode,
)
from app.live.live_broker_transport import LockedLiveBrokerTransport
from app.live.live_execution_claim_gate import LiveExecutionClaimGate
from app.live.live_execution_claim_models import (
    LiveExecutionClaimDecision,
)
from app.live.live_execution_journal_models import LiveExecutionState
from app.live.live_execution_journal_repository import SQLiteLiveExecutionJournal
from app.live.live_execution_preparation_service import (
    LockedLiveExecutionPreparationService,
)
from app.live.live_order_adapter import LockedLiveOrderAdapter
from app.live.live_order_idempotency_repository import (
    SQLiteLiveOrderIdempotencyStore,
)
from app.live.live_order_models import LiveOrderDecision
from app.live.live_order_safety import LiveOrderSafetySnapshot
from app.live.live_submission_boundary import LockedLiveSubmissionBoundary
from app.live.live_submission_coordinator import LockedLiveSubmissionCoordinator
from app.live.live_submission_coordinator_models import (
    LiveSubmissionCoordinatorDecision,
)
from app.live.risk_manager import LiveRiskManager
from app.live.risk_models import RiskLimits, RiskPortfolioSnapshot
from app.risk.kill_switch_models import KillSwitchSnapshot
from app.risk.kill_switch_service import KillSwitchService
from app.trading.order_models import OrderSide, OrderType, TradeOrder


NOW = datetime(2026, 10, 3, 1, 0, 0, tzinfo=timezone.utc)
TRADING_DATE = date(2026, 10, 3)


def _order() -> TradeOrder:
    return TradeOrder(
        order_id="order-phase6c-e2e-1",
        signal_id="signal-phase6c-e2e-1",
        code="7203",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=100,
        limit_price=2500.0,
        stop_price=None,
    )


def _portfolio() -> RiskPortfolioSnapshot:
    return RiskPortfolioSnapshot(
        trading_date=TRADING_DATE,
        cash_balance=10_000_000.0,
        total_exposure=0.0,
        current_equity=10_000_000.0,
        peak_equity=10_000_000.0,
        daily_realized_profit_loss=0.0,
        consecutive_losses=0,
        open_position_codes=(),
    )


def _kill_snapshot(*, manual_blocked: bool = False) -> KillSwitchSnapshot:
    return KillSwitchSnapshot(
        manual_blocked=manual_blocked,
        daily_loss_blocked=False,
        consecutive_loss_blocked=False,
        runtime_health_ok=True,
        heartbeat_alive=True,
        broker_available=True,
        evaluated_at=NOW,
    )


def _safety(
    *,
    safe_stop_active: bool = False,
    reconciliation_consistent: bool = True,
) -> LiveOrderSafetySnapshot:
    return LiveOrderSafetySnapshot(
        safe_stop_active=safe_stop_active,
        reconciliation_consistent=reconciliation_consistent,
        reconciliation_state=(
            "consistent" if reconciliation_consistent else "mismatch"
        ),
        evaluated_at=NOW,
    )


def _risk_manager() -> LiveRiskManager:
    return LiveRiskManager(
        limits=RiskLimits(
            max_position_count=5,
            max_position_value=1_000_000.0,
            max_total_exposure=5_000_000.0,
            minimum_cash_balance=500_000.0,
            max_daily_loss=50_000.0,
            max_drawdown_rate=0.10,
            max_consecutive_losses=3,
        )
    )


def _adapter(
    database_path,
    *,
    safety_snapshot_provider,
    kill_switch_snapshot_provider,
) -> LockedLiveOrderAdapter:
    return LockedLiveOrderAdapter(
        risk_manager=_risk_manager(),
        kill_switch_service=KillSwitchService(),
        portfolio_provider=_portfolio,
        kill_switch_snapshot_provider=kill_switch_snapshot_provider,
        idempotency_store=SQLiteLiveOrderIdempotencyStore(
            database_path,
            now_provider=lambda: NOW,
        ),
        safety_snapshot_provider=safety_snapshot_provider,
        runtime_armed=False,
        now_provider=lambda: NOW,
    )


def _journal(database_path) -> SQLiteLiveExecutionJournal:
    return SQLiteLiveExecutionJournal(database_path)


def test_real_components_reach_locked_transport_without_submission(tmp_path) -> None:
    database_path = tmp_path / "katana.db"
    journal = _journal(database_path)
    adapter = _adapter(
        database_path,
        safety_snapshot_provider=lambda: _safety(),
        kill_switch_snapshot_provider=lambda: _kill_snapshot(),
    )
    order = _order()
    intent = adapter.create_intent(order)

    preparation = LockedLiveExecutionPreparationService(
        boundary=adapter,
        journal=journal,
    ).prepare(intent)

    assert preparation.is_prepared
    assert preparation.boundary_result.decision is LiveOrderDecision.LOCKED
    assert preparation.journal_record is not None
    assert preparation.journal_record.state is LiveExecutionState.PREPARED

    claim = LiveExecutionClaimGate(
        journal=journal,
        kill_switch_service=KillSwitchService(),
        safety_snapshot_provider=lambda: _safety(),
        kill_switch_snapshot_provider=lambda: _kill_snapshot(),
        now_provider=lambda: NOW,
    ).claim(intent.idempotency_key)

    assert claim.decision is LiveExecutionClaimDecision.CLAIMED
    assert claim.journal_record.state is LiveExecutionState.CLAIMED

    submission_boundary = LockedLiveSubmissionBoundary(
        journal=journal,
        now_provider=lambda: NOW,
    )
    coordinator = LockedLiveSubmissionCoordinator(
        journal=journal,
        submission_boundary=submission_boundary,
        transport=LockedLiveBrokerTransport(
            execution_settings=ExecutionModeSettings(
                mode=TradingExecutionMode.PAPER,
                live_armed=False,
                live_confirmation=None,
            ),
            runtime_armed=False,
            now_provider=lambda: NOW,
        ),
        now_provider=lambda: NOW,
    )

    result = coordinator.evaluate(
        execution_key=intent.idempotency_key,
        order=order,
        trading_date=TRADING_DATE,
    )

    assert (
        result.decision
        is LiveSubmissionCoordinatorDecision.TRANSPORT_LOCKED
    )
    assert result.journal_record.state is LiveExecutionState.SUBMISSION_PENDING
    assert result.journal_record.submitted_at is None
    assert result.journal_record.broker_order_id is None


def test_real_adapter_safe_stop_blocks_before_journal_creation(tmp_path) -> None:
    database_path = tmp_path / "katana.db"
    journal = _journal(database_path)
    adapter = _adapter(
        database_path,
        safety_snapshot_provider=lambda: _safety(safe_stop_active=True),
        kill_switch_snapshot_provider=lambda: _kill_snapshot(),
    )
    intent = adapter.create_intent(_order())

    result = LockedLiveExecutionPreparationService(
        boundary=adapter,
        journal=journal,
    ).prepare(intent)

    assert result.boundary_result.decision is LiveOrderDecision.BLOCKED
    assert result.journal_record is None
    assert journal.get(intent.idempotency_key) is None


def test_real_adapter_reconciliation_blocks_before_journal_creation(
    tmp_path,
) -> None:
    database_path = tmp_path / "katana.db"
    journal = _journal(database_path)
    adapter = _adapter(
        database_path,
        safety_snapshot_provider=lambda: _safety(
            reconciliation_consistent=False
        ),
        kill_switch_snapshot_provider=lambda: _kill_snapshot(),
    )
    intent = adapter.create_intent(_order())

    result = LockedLiveExecutionPreparationService(
        boundary=adapter,
        journal=journal,
    ).prepare(intent)

    assert result.boundary_result.decision is LiveOrderDecision.BLOCKED
    assert result.journal_record is None
    assert journal.get(intent.idempotency_key) is None


def test_real_adapter_kill_switch_blocks_before_journal_creation(tmp_path) -> None:
    database_path = tmp_path / "katana.db"
    journal = _journal(database_path)
    adapter = _adapter(
        database_path,
        safety_snapshot_provider=lambda: _safety(),
        kill_switch_snapshot_provider=lambda: _kill_snapshot(
            manual_blocked=True
        ),
    )
    intent = adapter.create_intent(_order())

    result = LockedLiveExecutionPreparationService(
        boundary=adapter,
        journal=journal,
    ).prepare(intent)

    assert result.boundary_result.decision is LiveOrderDecision.BLOCKED
    assert result.journal_record is None
    assert journal.get(intent.idempotency_key) is None


def test_real_claim_gate_rechecks_safety_and_leaves_prepared(tmp_path) -> None:
    database_path = tmp_path / "katana.db"
    journal = _journal(database_path)
    adapter = _adapter(
        database_path,
        safety_snapshot_provider=lambda: _safety(),
        kill_switch_snapshot_provider=lambda: _kill_snapshot(),
    )
    intent = adapter.create_intent(_order())

    preparation = LockedLiveExecutionPreparationService(
        boundary=adapter,
        journal=journal,
    ).prepare(intent)
    assert preparation.is_prepared

    claim = LiveExecutionClaimGate(
        journal=journal,
        kill_switch_service=KillSwitchService(),
        safety_snapshot_provider=lambda: _safety(safe_stop_active=True),
        kill_switch_snapshot_provider=lambda: _kill_snapshot(),
        now_provider=lambda: NOW,
    ).claim(intent.idempotency_key)

    assert claim.decision is LiveExecutionClaimDecision.BLOCKED
    assert (
        journal.get_required(intent.idempotency_key).state
        is LiveExecutionState.PREPARED
    )


def test_durable_duplicate_after_restart_cannot_create_second_execution(
    tmp_path,
) -> None:
    database_path = tmp_path / "katana.db"
    journal = _journal(database_path)
    order = _order()

    first_adapter = _adapter(
        database_path,
        safety_snapshot_provider=lambda: _safety(),
        kill_switch_snapshot_provider=lambda: _kill_snapshot(),
    )
    first_intent = first_adapter.create_intent(order)
    first = LockedLiveExecutionPreparationService(
        boundary=first_adapter,
        journal=journal,
    ).prepare(first_intent)

    assert first.is_prepared
    assert first.newly_prepared

    restarted_adapter = _adapter(
        database_path,
        safety_snapshot_provider=lambda: _safety(),
        kill_switch_snapshot_provider=lambda: _kill_snapshot(),
    )
    restarted_intent = restarted_adapter.create_intent(order)
    second = LockedLiveExecutionPreparationService(
        boundary=restarted_adapter,
        journal=_journal(database_path),
    ).prepare(restarted_intent)

    assert second.boundary_result.decision is LiveOrderDecision.DUPLICATE
    assert second.is_prepared
    assert not second.newly_prepared
    assert second.journal_record is not None
    assert second.journal_record.execution_key == first_intent.idempotency_key


def test_no_real_submission_capability_is_exposed_by_e2e_components() -> None:
    forbidden = {
        "send",
        "send_order",
        "sendorder",
        "submit",
        "submit_order",
        "transmit",
        "execute_live_order",
    }
    component_types = (
        LockedLiveOrderAdapter,
        LockedLiveExecutionPreparationService,
        LiveExecutionClaimGate,
        LockedLiveSubmissionBoundary,
        LockedLiveSubmissionCoordinator,
        LockedLiveBrokerTransport,
    )

    for component_type in component_types:
        public_names = {
            name
            for name in dir(component_type)
            if not name.startswith("_")
        }
        assert forbidden.isdisjoint(public_names), component_type.__name__
