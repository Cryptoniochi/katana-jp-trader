"""Phase 6-D Step 6B end-to-end Live dry-run tests."""

from datetime import date, datetime, timezone
from types import SimpleNamespace

from app.live.execution_mode import ExecutionModeSettings, TradingExecutionMode
from app.live.final_live_readiness import FinalLiveReadinessGate
from app.live.live_dry_run_e2e_coordinator import LiveDryRunE2ECoordinator
from app.live.live_dry_run_e2e_models import LiveDryRunE2EDecision
from app.live.live_execution_claim_gate import LiveExecutionClaimGate
from app.live.live_execution_journal_models import LiveExecutionState
from app.live.live_execution_journal_repository import SQLiteLiveExecutionJournal
from app.live.live_execution_preparation_service import (
    LockedLiveExecutionPreparationService,
)
from app.live.live_order_adapter import (
    LIVE_ORDER_TRANSMISSION_ENABLED,
    LockedLiveOrderAdapter,
)
from app.live.live_order_models import LiveOrderDecision, LiveOrderIntent
from app.live.live_order_safety import LiveOrderSafetySnapshot
from app.live.live_submission_boundary import LockedLiveSubmissionBoundary
from app.live.live_transport_dry_run import SimulatedLiveBrokerTransport
from app.live.live_transport_dry_run_coordinator import (
    DryRunLiveSubmissionCoordinator,
)
from app.live.live_broker_transport import LIVE_BROKER_TRANSPORT_ENABLED
from app.live.locked_live_runtime_integration import (
    LOCKED_LIVE_RUNTIME_INTEGRATION_ENABLED,
)
from app.live.risk_models import RiskPortfolioSnapshot
from app.risk.kill_switch_models import KillSwitchSnapshot
from app.risk.kill_switch_service import KillSwitchService
from app.trading.order_models import OrderSide, OrderType, TradeOrder


NOW = datetime(2026, 10, 5, 8, 0, tzinfo=timezone.utc)
DAY = date(2026, 10, 5)


class BoundaryStub:
    def __init__(self, decision=LiveOrderDecision.LOCKED):
        self.decision = decision
        self.calls = 0

    def evaluate(self, intent):
        self.calls += 1
        return SimpleNamespace(intent=intent, decision=self.decision)


def _settings():
    return ExecutionModeSettings(
        mode=TradingExecutionMode.LIVE,
        live_armed=True,
        live_confirmation="KATANA-LIVE-2026-10-05",
    )


def _order():
    return TradeOrder(
        order_id="dry-e2e-order-1",
        signal_id="dry-e2e-signal-1",
        code="7203",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=100,
        limit_price=1000.0,
        stop_price=None,
    )


def _intent():
    order = _order()
    return LiveOrderIntent(
        order=order,
        idempotency_key=LockedLiveOrderAdapter.create_idempotency_key(order),
        created_at=NOW,
    )


def _safety(*, blocked=False):
    return LiveOrderSafetySnapshot(
        safe_stop_active=blocked,
        reconciliation_consistent=not blocked,
        reconciliation_state="safe_stop" if blocked else "consistent",
        evaluated_at=NOW,
    )


def _kill(*, manual=False):
    return KillSwitchSnapshot(
        manual_blocked=manual,
        daily_loss_blocked=False,
        consecutive_loss_blocked=False,
        runtime_health_ok=True,
        heartbeat_alive=True,
        broker_available=True,
        evaluated_at=NOW,
    )


def _portfolio():
    return RiskPortfolioSnapshot(
        trading_date=DAY,
        cash_balance=1_000_000.0,
        total_exposure=0.0,
        current_equity=1_000_000.0,
        peak_equity=1_000_000.0,
        daily_realized_profit_loss=0.0,
        consecutive_losses=0,
        open_position_codes=frozenset(),
    )


def _readiness(*, manual=False):
    return FinalLiveReadinessGate(
        manual_blocked_provider=lambda: manual,
        daily_profit_loss_provider=lambda: 0.0,
        consecutive_loss_count_provider=lambda: 0,
        runtime_health_ok_provider=lambda: True,
        heartbeat_alive_provider=lambda: True,
        broker_available_provider=lambda: True,
        portfolio_provider=_portfolio,
        safety_snapshot_provider=_safety,
        kill_switch_snapshot_provider=lambda: _kill(manual=manual),
        now_provider=lambda: NOW,
    )


def _runtime(
    tmp_path,
    *,
    readiness=None,
    boundary=None,
    claim_safety_provider=None,
    claim_kill_provider=None,
):
    journal = SQLiteLiveExecutionJournal(
        tmp_path / "live_dry_run.db",
        now_provider=lambda: NOW,
    )
    preparation = LockedLiveExecutionPreparationService(
        boundary=boundary or BoundaryStub(),
        journal=journal,
    )
    claim_gate = LiveExecutionClaimGate(
        journal=journal,
        kill_switch_service=KillSwitchService(),
        safety_snapshot_provider=claim_safety_provider or _safety,
        kill_switch_snapshot_provider=claim_kill_provider or _kill,
        now_provider=lambda: NOW,
    )
    submission_boundary = LockedLiveSubmissionBoundary(
        journal=journal,
        now_provider=lambda: NOW,
    )
    transport = SimulatedLiveBrokerTransport(
        execution_settings=_settings(),
        now_provider=lambda: NOW,
    )
    submission = DryRunLiveSubmissionCoordinator(
        journal=journal,
        submission_boundary=submission_boundary,
        transport=transport,
        now_provider=lambda: NOW,
    )
    coordinator = LiveDryRunE2ECoordinator(
        readiness_gate=readiness or _readiness(),
        preparation_service=preparation,
        claim_gate=claim_gate,
        submission_coordinator=submission,
        execution_settings=_settings(),
        now_provider=lambda: NOW,
    )
    return coordinator, journal


def test_e2e_dry_run_reaches_simulated_transport_and_stays_pending(tmp_path):
    coordinator, journal = _runtime(tmp_path)
    intent = _intent()

    result = coordinator.run(intent=intent, trading_date=DAY)

    assert result.decision is LiveDryRunE2EDecision.SIMULATED_TRANSPORT_REACHED
    assert result.simulated_transport_reached is True
    assert result.readiness_report.activation_ready is True
    assert result.readiness_report.transport_ready is False
    assert result.readiness_report.live_order_ready is False
    assert result.preparation_result is not None
    assert result.preparation_result.is_prepared is True
    assert result.claim_result is not None
    assert result.claim_result.is_claimed is True
    assert result.submission_result is not None
    assert (
        journal.get_required(intent.idempotency_key).state
        is LiveExecutionState.SUBMISSION_PENDING
    )
    assert journal.get_required(intent.idempotency_key).broker_order_id is None
    assert (
        result.submission_result.transport_result.simulated_broker_order_id
        .startswith("DRYRUN-")
    )


def test_readiness_block_happens_before_journal_preparation(tmp_path):
    coordinator, journal = _runtime(
        tmp_path,
        readiness=_readiness(manual=True),
    )

    result = coordinator.run(intent=_intent(), trading_date=DAY)

    assert result.decision is LiveDryRunE2EDecision.BLOCKED_READINESS
    assert journal.count() == 0
    assert result.preparation_result is None
    assert result.claim_result is None
    assert result.submission_result is None


def test_locked_preparation_block_never_claims_or_submits(tmp_path):
    coordinator, journal = _runtime(
        tmp_path,
        boundary=BoundaryStub(LiveOrderDecision.BLOCKED),
    )

    result = coordinator.run(intent=_intent(), trading_date=DAY)

    assert result.decision is LiveDryRunE2EDecision.BLOCKED_PREPARATION
    assert journal.count() == 0
    assert result.claim_result is None
    assert result.submission_result is None


def test_fresh_claim_gate_can_block_after_preparation(tmp_path):
    coordinator, journal = _runtime(
        tmp_path,
        claim_safety_provider=lambda: _safety(blocked=True),
    )
    intent = _intent()

    result = coordinator.run(intent=intent, trading_date=DAY)

    assert result.decision is LiveDryRunE2EDecision.BLOCKED_CLAIM
    assert result.claim_result is not None
    assert result.claim_result.is_blocked is True
    assert (
        journal.get_required(intent.idempotency_key).state
        is LiveExecutionState.PREPARED
    )
    assert result.submission_result is None


def test_all_hard_live_locks_remain_closed():
    assert LIVE_ORDER_TRANSMISSION_ENABLED is False
    assert LIVE_BROKER_TRANSPORT_ENABLED is False
    assert LOCKED_LIVE_RUNTIME_INTEGRATION_ENABLED is False


def test_e2e_coordinator_exposes_no_submit_or_transport_method(tmp_path):
    coordinator, _ = _runtime(tmp_path)

    assert not hasattr(coordinator, "submit")
    assert not hasattr(coordinator, "submit_order")
    assert not hasattr(coordinator, "send_order")
    assert not hasattr(coordinator, "sendorder")
    assert not hasattr(coordinator, "transmit")
