from datetime import date, datetime, timezone

import pytest

from app.live.execution_mode import (
    ExecutionModeSettings,
    TradingExecutionMode,
)
from app.live.live_broker_transport import LockedLiveBrokerTransport
from app.live.live_broker_transport_models import (
    LiveTransportDecision,
    LiveTransportLockReason,
)
from app.live.live_execution_journal_models import LiveExecutionState
from app.live.live_execution_journal_repository import (
    LiveExecutionTransitionError,
    SQLiteLiveExecutionJournal,
)
from app.live.live_submission_boundary import LockedLiveSubmissionBoundary
from app.live.live_submission_coordinator import LockedLiveSubmissionCoordinator
from app.live.live_submission_coordinator_models import (
    LiveSubmissionCoordinatorDecision,
)
from app.trading.order_models import OrderSide, OrderType, TradeOrder


NOW = datetime(2026, 10, 3, 1, 0, 0, tzinfo=timezone.utc)
TRADING_DATE = date(2026, 10, 3)
EXECUTION_KEY = "execution-key-1"
FINGERPRINT = "fingerprint-1"


def _order(
    *,
    order_id: str = "order-1",
    signal_id: str = "signal-1",
) -> TradeOrder:
    return TradeOrder(
        order_id=order_id,
        signal_id=signal_id,
        code="7203",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=100,
        limit_price=2500.0,
        stop_price=None,
    )


def _journal(tmp_path) -> SQLiteLiveExecutionJournal:
    return SQLiteLiveExecutionJournal(tmp_path / "katana.db")


def _prepare_and_claim(
    journal: SQLiteLiveExecutionJournal,
    order: TradeOrder,
) -> None:
    journal.prepare(
        execution_key=EXECUTION_KEY,
        order_fingerprint=FINGERPRINT,
        order_id=order.order_id,
        signal_id=order.signal_id,
    )
    journal.claim(EXECUTION_KEY)


def _coordinator(
    journal: SQLiteLiveExecutionJournal,
    *,
    transport_runtime_armed: bool = False,
) -> LockedLiveSubmissionCoordinator:
    boundary = LockedLiveSubmissionBoundary(
        journal=journal,
        now_provider=lambda: NOW,
    )
    transport = LockedLiveBrokerTransport(
        execution_settings=ExecutionModeSettings(
            mode=TradingExecutionMode.PAPER,
            live_armed=False,
            live_confirmation=None,
        ),
        runtime_armed=transport_runtime_armed,
        now_provider=lambda: NOW,
    )
    return LockedLiveSubmissionCoordinator(
        journal=journal,
        submission_boundary=boundary,
        transport=transport,
        now_provider=lambda: NOW,
    )


def test_claimed_execution_reaches_locked_transport_and_stays_pending(
    tmp_path,
) -> None:
    journal = _journal(tmp_path)
    order = _order()
    _prepare_and_claim(journal, order)
    coordinator = _coordinator(journal)

    result = coordinator.evaluate(
        execution_key=EXECUTION_KEY,
        order=order,
        trading_date=TRADING_DATE,
    )

    assert (
        result.decision
        is LiveSubmissionCoordinatorDecision.TRANSPORT_LOCKED
    )
    assert result.transport_result.decision is LiveTransportDecision.LOCKED
    assert (
        result.transport_result.reason
        is LiveTransportLockReason.STATIC_LOCK
    )
    assert result.journal_record.state is LiveExecutionState.SUBMISSION_PENDING
    assert (
        journal.get_required(EXECUTION_KEY).state
        is LiveExecutionState.SUBMISSION_PENDING
    )


def test_locked_transport_does_not_mark_unknown(tmp_path) -> None:
    journal = _journal(tmp_path)
    order = _order()
    _prepare_and_claim(journal, order)

    result = _coordinator(journal).evaluate(
        execution_key=EXECUTION_KEY,
        order=order,
        trading_date=TRADING_DATE,
    )

    assert result.journal_record.state is LiveExecutionState.SUBMISSION_PENDING
    assert result.journal_record.unknown_at is None
    assert journal.get_required(EXECUTION_KEY).unknown_at is None


def test_locked_transport_does_not_mark_submitted(tmp_path) -> None:
    journal = _journal(tmp_path)
    order = _order()
    _prepare_and_claim(journal, order)

    result = _coordinator(journal).evaluate(
        execution_key=EXECUTION_KEY,
        order=order,
        trading_date=TRADING_DATE,
    )

    assert result.journal_record.state is LiveExecutionState.SUBMISSION_PENDING
    assert result.journal_record.submitted_at is None
    assert result.journal_record.broker_order_id is None


@pytest.mark.parametrize(
    "initial_state",
    [
        LiveExecutionState.PREPARED,
        LiveExecutionState.SUBMISSION_PENDING,
    ],
)
def test_only_claimed_execution_may_start_coordinator(
    tmp_path,
    initial_state,
) -> None:
    journal = _journal(tmp_path)
    order = _order()
    journal.prepare(
        execution_key=EXECUTION_KEY,
        order_fingerprint=FINGERPRINT,
        order_id=order.order_id,
        signal_id=order.signal_id,
    )
    if initial_state is LiveExecutionState.SUBMISSION_PENDING:
        journal.claim(EXECUTION_KEY)
        journal.mark_submission_pending(EXECUTION_KEY)

    with pytest.raises(LiveExecutionTransitionError):
        _coordinator(journal).evaluate(
            execution_key=EXECUTION_KEY,
            order=order,
            trading_date=TRADING_DATE,
        )

    assert journal.get_required(EXECUTION_KEY).state is initial_state


def test_order_id_must_match_journal_before_pending_transition(tmp_path) -> None:
    journal = _journal(tmp_path)
    original = _order()
    _prepare_and_claim(journal, original)

    with pytest.raises(ValueError, match="order_id"):
        _coordinator(journal).evaluate(
            execution_key=EXECUTION_KEY,
            order=_order(order_id="different-order"),
            trading_date=TRADING_DATE,
        )

    assert (
        journal.get_required(EXECUTION_KEY).state
        is LiveExecutionState.CLAIMED
    )


def test_signal_id_must_match_journal_before_pending_transition(tmp_path) -> None:
    journal = _journal(tmp_path)
    original = _order()
    _prepare_and_claim(journal, original)

    with pytest.raises(ValueError, match="signal_id"):
        _coordinator(journal).evaluate(
            execution_key=EXECUTION_KEY,
            order=_order(signal_id="different-signal"),
            trading_date=TRADING_DATE,
        )

    assert (
        journal.get_required(EXECUTION_KEY).state
        is LiveExecutionState.CLAIMED
    )


def test_second_coordinator_attempt_cannot_retry_pending_execution(
    tmp_path,
) -> None:
    journal = _journal(tmp_path)
    order = _order()
    _prepare_and_claim(journal, order)
    coordinator = _coordinator(journal)

    coordinator.evaluate(
        execution_key=EXECUTION_KEY,
        order=order,
        trading_date=TRADING_DATE,
    )

    with pytest.raises(LiveExecutionTransitionError):
        coordinator.evaluate(
            execution_key=EXECUTION_KEY,
            order=order,
            trading_date=TRADING_DATE,
        )

    assert (
        journal.get_required(EXECUTION_KEY).state
        is LiveExecutionState.SUBMISSION_PENDING
    )


def test_recovery_still_freezes_pending_as_unknown(tmp_path) -> None:
    journal = _journal(tmp_path)
    order = _order()
    _prepare_and_claim(journal, order)
    coordinator = _coordinator(journal)

    coordinator.evaluate(
        execution_key=EXECUTION_KEY,
        order=order,
        trading_date=TRADING_DATE,
    )

    recovery = coordinator.submission_boundary.recover_if_ambiguous(
        EXECUTION_KEY
    )

    assert recovery is not None
    assert recovery.journal_record.state is LiveExecutionState.UNKNOWN
    assert journal.get_required(EXECUTION_KEY).state is LiveExecutionState.UNKNOWN


def test_coordinator_exposes_no_submission_or_send_method() -> None:
    forbidden = {
        "submit",
        "submit_order",
        "send",
        "send_order",
        "sendorder",
        "transmit",
        "execute_live_order",
        "mark_submitted",
    }

    public_names = {
        name
        for name in dir(LockedLiveSubmissionCoordinator)
        if not name.startswith("_")
    }

    assert forbidden.isdisjoint(public_names)


def test_coordinator_constructor_accepts_no_broker_or_network_client() -> None:
    names = set(LockedLiveSubmissionCoordinator.__init__.__code__.co_varnames)
    forbidden = {
        "broker",
        "broker_adapter",
        "client",
        "http_client",
        "session",
        "transport_client",
    }

    assert forbidden.isdisjoint(names)
