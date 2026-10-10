"""Phase 6-F activated live transport/coordinator tests."""
from __future__ import annotations

from datetime import date, datetime, timezone

from app.live.activated_live_broker_transport import (
    ActivatedKabuStationLiveTransport,
    ActivatedLiveTransportDecision,
)
from app.live.activated_live_submission_coordinator import (
    ActivatedLiveSubmissionCoordinator,
    ActivatedLiveSubmissionDecision,
)
from app.live.execution_mode import ExecutionModeSettings, TradingExecutionMode
from app.live.live_broker_transport_models import LiveTransportRequest
from app.live.live_execution_journal_models import LiveExecutionState
from app.live.live_execution_journal_repository import SQLiteLiveExecutionJournal
from app.live.live_order_adapter import LockedLiveOrderAdapter
from app.live.live_submission_boundary import LockedLiveSubmissionBoundary
from app.trading.order_models import OrderSide, OrderType, TradeOrder


NOW = datetime(2026, 10, 10, 1, 0, tzinfo=timezone.utc)
DAY = date(2026, 10, 10)


class _Sender:
    def __init__(self, *, fail=False):
        self.calls = 0
        self.fail = fail

    def send_once(self, order):
        self.calls += 1
        if self.fail:
            raise TimeoutError("ambiguous timeout")
        return "broker-123"


def _order():
    return TradeOrder(
        order_id="order-1",
        signal_id="signal-1",
        code="7203",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=100,
    )


def _settings():
    return ExecutionModeSettings(
        mode=TradingExecutionMode.LIVE,
        live_armed=True,
        live_confirmation=f"KATANA-LIVE-{DAY.isoformat()}",
    )


def _claimed(tmp_path):
    journal = SQLiteLiveExecutionJournal(
        tmp_path / "katana.db",
        now_provider=lambda: NOW,
    )
    order = _order()
    journal.prepare(
        "exec-1",
        order_fingerprint=LockedLiveOrderAdapter.create_order_fingerprint(order),
        order_id=order.order_id,
        signal_id=order.signal_id,
    )
    journal.claim("exec-1")
    return journal, order


def test_transport_default_activation_lock_makes_no_sender_call():
    sender = _Sender()
    transport = ActivatedKabuStationLiveTransport(
        sender=sender,
        execution_settings=_settings(),
        now_provider=lambda: NOW,
    )
    result = transport.submit(
        LiveTransportRequest("exec-1", _order(), NOW),
        trading_date=DAY,
    )
    assert result.decision is ActivatedLiveTransportDecision.BLOCKED
    assert sender.calls == 0


def test_transport_runtime_lock_makes_no_sender_call():
    sender = _Sender()
    transport = ActivatedKabuStationLiveTransport(
        sender=sender,
        execution_settings=_settings(),
        activation_enabled=True,
        runtime_armed=False,
        now_provider=lambda: NOW,
    )
    result = transport.submit(
        LiveTransportRequest("exec-1", _order(), NOW),
        trading_date=DAY,
    )
    assert result.decision is ActivatedLiveTransportDecision.BLOCKED
    assert sender.calls == 0


def test_coordinator_confirmed_order_id_marks_submitted(tmp_path):
    journal, order = _claimed(tmp_path)
    sender = _Sender()
    transport = ActivatedKabuStationLiveTransport(
        sender=sender,
        execution_settings=_settings(),
        activation_enabled=True,
        runtime_armed=True,
        now_provider=lambda: NOW,
    )
    coordinator = ActivatedLiveSubmissionCoordinator(
        journal=journal,
        submission_boundary=LockedLiveSubmissionBoundary(
            journal=journal, now_provider=lambda: NOW
        ),
        transport=transport,
        now_provider=lambda: NOW,
    )

    result = coordinator.submit(
        execution_key="exec-1",
        order=order,
        trading_date=DAY,
    )

    assert result.decision is ActivatedLiveSubmissionDecision.SUBMITTED
    assert result.journal_record.state is LiveExecutionState.SUBMITTED
    assert result.journal_record.broker_order_id == "broker-123"
    assert sender.calls == 1


def test_coordinator_ambiguous_transport_failure_freezes_unknown(tmp_path):
    journal, order = _claimed(tmp_path)
    sender = _Sender(fail=True)
    transport = ActivatedKabuStationLiveTransport(
        sender=sender,
        execution_settings=_settings(),
        activation_enabled=True,
        runtime_armed=True,
        now_provider=lambda: NOW,
    )
    coordinator = ActivatedLiveSubmissionCoordinator(
        journal=journal,
        submission_boundary=LockedLiveSubmissionBoundary(
            journal=journal, now_provider=lambda: NOW
        ),
        transport=transport,
        now_provider=lambda: NOW,
    )

    result = coordinator.submit(
        execution_key="exec-1",
        order=order,
        trading_date=DAY,
    )

    assert result.decision is ActivatedLiveSubmissionDecision.UNKNOWN
    assert result.journal_record.state is LiveExecutionState.UNKNOWN
    assert sender.calls == 1
