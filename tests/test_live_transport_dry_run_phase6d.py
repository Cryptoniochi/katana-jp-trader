"""Phase 6-D Step 6A simulated Live transport tests."""

from __future__ import annotations

import inspect
from datetime import date, datetime, timezone

import pytest

from app.live.execution_mode import (
    ExecutionModeSettings,
    LiveTradingLockError,
    TradingExecutionMode,
)
from app.live.live_broker_transport import LIVE_BROKER_TRANSPORT_ENABLED
from app.live.live_execution_journal_models import LiveExecutionState
from app.live.live_execution_journal_repository import SQLiteLiveExecutionJournal
from app.live.live_order_adapter import (
    LIVE_ORDER_TRANSMISSION_ENABLED,
    LockedLiveOrderAdapter,
)
from app.live.live_submission_boundary import LockedLiveSubmissionBoundary
from app.live.live_transport_dry_run import SimulatedLiveBrokerTransport
from app.live.live_transport_dry_run_coordinator import DryRunLiveSubmissionCoordinator
from app.live.live_transport_dry_run_models import (
    DryRunSubmissionDecision,
    SimulatedLiveTransportDecision,
)
from app.live.locked_live_runtime_integration import (
    LOCKED_LIVE_RUNTIME_INTEGRATION_ENABLED,
)
from app.trading.order_models import OrderSide, OrderType, TradeOrder


NOW = datetime(2026, 10, 5, 7, 30, tzinfo=timezone.utc)
DAY = date(2026, 10, 5)
KEY = "dry-run-execution-1"


def _order() -> TradeOrder:
    return TradeOrder(
        order_id="dry-run-order-1",
        signal_id="dry-run-signal-1",
        code="7203",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=100,
        limit_price=2500.0,
        stop_price=None,
    )


def _settings() -> ExecutionModeSettings:
    return ExecutionModeSettings(
        mode=TradingExecutionMode.LIVE,
        live_armed=True,
        live_confirmation="KATANA-LIVE-2026-10-05",
    )


def _coordinator(tmp_path):
    journal = SQLiteLiveExecutionJournal(
        tmp_path / "live_dry_run.db",
        now_provider=lambda: NOW,
    )
    boundary = LockedLiveSubmissionBoundary(
        journal=journal,
        now_provider=lambda: NOW,
    )
    transport = SimulatedLiveBrokerTransport(
        execution_settings=_settings(),
        now_provider=lambda: NOW,
    )
    coordinator = DryRunLiveSubmissionCoordinator(
        journal=journal,
        submission_boundary=boundary,
        transport=transport,
        now_provider=lambda: NOW,
    )
    return journal, coordinator


def _prepare_and_claim(journal, order):
    fingerprint = LockedLiveOrderAdapter.create_order_fingerprint(order)
    journal.prepare(
        KEY,
        order_fingerprint=fingerprint,
        order_id=order.order_id,
        signal_id=order.signal_id,
        detail="Phase 6-D Step 6A dry-run only.",
    )
    journal.claim(KEY)


def test_dry_run_reaches_simulated_transport_without_marking_submitted(tmp_path):
    journal, coordinator = _coordinator(tmp_path)
    order = _order()
    _prepare_and_claim(journal, order)

    result = coordinator.evaluate(
        execution_key=KEY,
        order=order,
        trading_date=DAY,
    )

    assert result.decision is DryRunSubmissionDecision.SIMULATED_TRANSPORT_REACHED
    assert (
        result.transport_result.decision
        is SimulatedLiveTransportDecision.SIMULATED_ACCEPTED
    )
    assert result.transport_result.simulated_broker_order_id.startswith("DRYRUN-")
    assert journal.get_required(KEY).state is LiveExecutionState.SUBMISSION_PENDING
    assert journal.get_required(KEY).broker_order_id is None


def test_dry_run_requires_daily_live_authorization(tmp_path):
    journal = SQLiteLiveExecutionJournal(tmp_path / "dry.db")
    boundary = LockedLiveSubmissionBoundary(journal=journal)
    transport = SimulatedLiveBrokerTransport(
        execution_settings=ExecutionModeSettings(),
        now_provider=lambda: NOW,
    )
    coordinator = DryRunLiveSubmissionCoordinator(
        journal=journal,
        submission_boundary=boundary,
        transport=transport,
        now_provider=lambda: NOW,
    )
    order = _order()
    _prepare_and_claim(journal, order)

    with pytest.raises(LiveTradingLockError):
        coordinator.evaluate(execution_key=KEY, order=order, trading_date=DAY)

    assert journal.get_required(KEY).state is LiveExecutionState.SUBMISSION_PENDING
    assert journal.get_required(KEY).broker_order_id is None


def test_dry_run_rejects_order_fingerprint_mismatch_before_pending(tmp_path):
    journal, coordinator = _coordinator(tmp_path)
    original = _order()
    _prepare_and_claim(journal, original)
    changed = TradeOrder(
        order_id=original.order_id,
        signal_id=original.signal_id,
        code=original.code,
        side=original.side,
        order_type=original.order_type,
        quantity=200,
        limit_price=original.limit_price,
        stop_price=original.stop_price,
    )

    with pytest.raises(ValueError, match="fingerprint"):
        coordinator.evaluate(execution_key=KEY, order=changed, trading_date=DAY)

    assert journal.get_required(KEY).state is LiveExecutionState.CLAIMED


def test_simulated_receipt_is_deterministic(tmp_path):
    journal, coordinator = _coordinator(tmp_path)
    order = _order()
    _prepare_and_claim(journal, order)
    result = coordinator.evaluate(execution_key=KEY, order=order, trading_date=DAY)
    receipt = result.transport_result.simulated_broker_order_id
    assert receipt.startswith("DRYRUN-")
    assert len(receipt) == len("DRYRUN-") + 20


def test_step6a_keeps_all_live_hard_locks_closed():
    assert LIVE_ORDER_TRANSMISSION_ENABLED is False
    assert LIVE_BROKER_TRANSPORT_ENABLED is False
    assert LOCKED_LIVE_RUNTIME_INTEGRATION_ENABLED is False


def test_simulated_transport_contains_no_network_or_broker_client():
    source = inspect.getsource(SimulatedLiveBrokerTransport)
    forbidden = (
        "requests.",
        "httpx.",
        "urllib.",
        "KabuStationClient",
        "BrokerAdapter",
        "sendorder",
        "send_order",
        ".post(",
        ".put(",
        ".request(",
    )
    for token in forbidden:
        assert token not in source


def test_existing_locked_transport_and_coordinator_are_not_modified_for_dry_run():
    import app.live.live_broker_transport as locked_transport
    import app.live.live_submission_coordinator as locked_coordinator

    assert "SimulatedLiveBrokerTransport" not in inspect.getsource(locked_transport)
    assert "DryRunLiveSubmissionCoordinator" not in inspect.getsource(locked_coordinator)
