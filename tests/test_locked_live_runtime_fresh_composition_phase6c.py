"""Phase 6-C Step 4B-2 integration tests for freshness-aware composition."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from app.live.live_execution_claim_models import LiveExecutionClaimDecision
from app.live.live_execution_journal_models import LiveExecutionState
from app.live.live_order_models import LiveOrderDecision
from app.live.locked_live_runtime_fresh_composition import FreshLockedLiveRuntimeFactory
from app.live.risk_manager import LiveRiskManager
from app.live.risk_models import RiskLimits, RiskPortfolioSnapshot
from app.risk.kill_switch_models import KillSwitchSnapshot
from app.trading.order_models import OrderSide, OrderType, TradeOrder


NOW = datetime(2026, 10, 3, 4, 30, 0, tzinfo=timezone.utc)
TRADING_DATE = date(2026, 10, 3)


@dataclass(frozen=True)
class _Report:
    generated_at: datetime
    state: str = "consistent"
    consistent: bool = True
    live_order_ready: bool = False


class _MutableReportProvider:
    def __init__(self, report):
        self.report = report

    def __call__(self):
        return self.report


def _portfolio():
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


def _kill_snapshot():
    return KillSwitchSnapshot(
        manual_blocked=False,
        daily_loss_blocked=False,
        consecutive_loss_blocked=False,
        runtime_health_ok=True,
        heartbeat_alive=True,
        broker_available=True,
        evaluated_at=NOW,
    )


def _risk_manager():
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


def _order():
    return TradeOrder(
        order_id="step4b2-order",
        signal_id="step4b2-signal",
        code="7203",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=100,
        limit_price=2500.0,
        stop_price=None,
    )


def _bundle(tmp_path, report_provider):
    return FreshLockedLiveRuntimeFactory.create(
        database_path=tmp_path / "katana.db",
        risk_manager=_risk_manager(),
        portfolio_provider=_portfolio,
        reconciliation_report_provider=report_provider,
        fault_tolerance_attempt_provider=lambda: None,
        kill_switch_snapshot_provider=_kill_snapshot,
        now_provider=lambda: NOW,
    )


def test_stale_report_blocks_before_idempotency_and_journal(tmp_path):
    reports = _MutableReportProvider(
        _Report(generated_at=NOW - timedelta(minutes=3))
    )
    bundle = _bundle(tmp_path, reports)
    intent = bundle.order_adapter.create_intent(_order())

    prepared = bundle.preparation_service.prepare(intent)

    assert prepared.boundary_result.decision is LiveOrderDecision.BLOCKED
    assert prepared.journal_record is None
    assert bundle.journal.get(intent.idempotency_key) is None
    assert bundle.idempotency_store.get(intent.idempotency_key) is None


def test_fresh_report_allows_locked_preparation(tmp_path):
    reports = _MutableReportProvider(
        _Report(generated_at=NOW - timedelta(seconds=30))
    )
    bundle = _bundle(tmp_path, reports)
    intent = bundle.order_adapter.create_intent(_order())

    prepared = bundle.preparation_service.prepare(intent)

    assert prepared.boundary_result.decision is LiveOrderDecision.LOCKED
    assert prepared.journal_record is not None
    assert prepared.journal_record.state is LiveExecutionState.PREPARED


def test_report_becoming_stale_blocks_claim_and_preserves_prepared(tmp_path):
    reports = _MutableReportProvider(
        _Report(generated_at=NOW - timedelta(seconds=30))
    )
    bundle = _bundle(tmp_path, reports)
    intent = bundle.order_adapter.create_intent(_order())
    prepared = bundle.preparation_service.prepare(intent)

    assert prepared.journal_record is not None
    assert prepared.journal_record.state is LiveExecutionState.PREPARED

    reports.report = _Report(generated_at=NOW - timedelta(minutes=3))

    claimed = bundle.claim_gate.claim(intent.idempotency_key)

    assert claimed.decision is LiveExecutionClaimDecision.BLOCKED
    assert claimed.journal_record.state is LiveExecutionState.PREPARED
    assert bundle.journal.get_required(intent.idempotency_key).state is LiveExecutionState.PREPARED


def test_missing_report_blocks_preparation_without_durable_execution(tmp_path):
    reports = _MutableReportProvider(None)
    bundle = _bundle(tmp_path, reports)
    intent = bundle.order_adapter.create_intent(_order())

    prepared = bundle.preparation_service.prepare(intent)

    assert prepared.boundary_result.decision is LiveOrderDecision.BLOCKED
    assert prepared.journal_record is None
    assert bundle.journal.get(intent.idempotency_key) is None


def test_same_runtime_safety_provider_is_shared_by_adapter_and_claim_gate(tmp_path):
    reports = _MutableReportProvider(_Report(generated_at=NOW))
    bundle = _bundle(tmp_path, reports)

    assert (
        bundle.order_adapter.safety_snapshot_provider
        is bundle.claim_gate.safety_snapshot_provider
    )


def test_fresh_state_can_claim_but_transport_remains_runtime_disarmed(tmp_path):
    reports = _MutableReportProvider(_Report(generated_at=NOW))
    bundle = _bundle(tmp_path, reports)
    order = _order()
    intent = bundle.order_adapter.create_intent(order)
    prepared = bundle.preparation_service.prepare(intent)

    claimed = bundle.claim_gate.claim(intent.idempotency_key)

    assert prepared.journal_record is not None
    assert claimed.decision is LiveExecutionClaimDecision.CLAIMED
    assert claimed.journal_record.state is LiveExecutionState.CLAIMED
    assert bundle.order_adapter.runtime_armed is False
    assert bundle.transport.runtime_armed is False
