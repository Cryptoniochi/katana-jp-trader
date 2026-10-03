from datetime import datetime, timedelta, timezone

import pytest

from app.live.live_execution_journal_models import LiveExecutionState
from app.live.live_execution_journal_repository import (
    LiveExecutionAlreadyClaimedError,
    LiveExecutionJournalConflictError,
    LiveExecutionTransitionError,
    SQLiteLiveExecutionJournal,
)


BASE = datetime(2026, 10, 3, 3, 30, tzinfo=timezone.utc)


class Clock:
    def __init__(self):
        self.value = BASE

    def __call__(self):
        return self.value

    def advance(self):
        self.value += timedelta(seconds=1)


def _journal(tmp_path, clock):
    return SQLiteLiveExecutionJournal(
        tmp_path / "katana.db",
        now_provider=clock,
    )


def _prepare(journal):
    return journal.prepare(
        "exec-key-1",
        order_fingerprint="fingerprint-1",
        order_id="order-1",
        signal_id="signal-1",
    )


def test_prepare_is_durable_and_idempotent(tmp_path):
    clock = Clock()
    journal = _journal(tmp_path, clock)

    first = _prepare(journal)
    second = _prepare(journal)
    reopened = _journal(tmp_path, clock).get_required("exec-key-1")

    assert first.state is LiveExecutionState.PREPARED
    assert second == first
    assert reopened == first
    assert journal.count() == 1


def test_prepare_rejects_same_key_with_different_content(tmp_path):
    clock = Clock()
    journal = _journal(tmp_path, clock)
    _prepare(journal)

    with pytest.raises(LiveExecutionJournalConflictError):
        journal.prepare(
            "exec-key-1",
            order_fingerprint="different",
            order_id="order-1",
            signal_id="signal-1",
        )


def test_claim_is_atomic_and_cannot_be_reclaimed_after_restart(tmp_path):
    clock = Clock()
    journal = _journal(tmp_path, clock)
    _prepare(journal)
    clock.advance()

    claimed = journal.claim("exec-key-1")
    assert claimed.state is LiveExecutionState.CLAIMED
    assert claimed.claimed_at == clock.value

    reopened = _journal(tmp_path, clock)
    with pytest.raises(LiveExecutionAlreadyClaimedError):
        reopened.claim("exec-key-1")


def test_submission_pending_cannot_be_reclaimed(tmp_path):
    clock = Clock()
    journal = _journal(tmp_path, clock)
    _prepare(journal)
    clock.advance()
    journal.claim("exec-key-1")
    clock.advance()

    pending = journal.mark_submission_pending("exec-key-1")
    assert pending.state is LiveExecutionState.SUBMISSION_PENDING

    with pytest.raises(LiveExecutionAlreadyClaimedError):
        journal.claim("exec-key-1")


def test_unknown_freezes_ambiguous_submission_and_blocks_reclaim(tmp_path):
    clock = Clock()
    journal = _journal(tmp_path, clock)
    _prepare(journal)
    clock.advance()
    journal.claim("exec-key-1")
    clock.advance()
    journal.mark_submission_pending("exec-key-1")
    clock.advance()

    unknown = journal.mark_unknown(
        "exec-key-1",
        detail="Transport outcome could not be proven.",
    )

    assert unknown.state is LiveExecutionState.UNKNOWN
    assert unknown.unknown_at == clock.value
    assert unknown.detail == "Transport outcome could not be proven."

    reopened = _journal(tmp_path, clock)
    with pytest.raises(LiveExecutionAlreadyClaimedError):
        reopened.claim("exec-key-1")
    with pytest.raises(LiveExecutionTransitionError):
        reopened.mark_submission_pending("exec-key-1")


def test_submitted_requires_pending_and_broker_order_id(tmp_path):
    clock = Clock()
    journal = _journal(tmp_path, clock)
    _prepare(journal)
    clock.advance()
    journal.claim("exec-key-1")

    with pytest.raises(LiveExecutionTransitionError):
        journal.mark_submitted(
            "exec-key-1",
            broker_order_id="broker-1",
        )

    clock.advance()
    journal.mark_submission_pending("exec-key-1")
    clock.advance()
    submitted = journal.mark_submitted(
        "exec-key-1",
        broker_order_id="broker-1",
    )

    assert submitted.state is LiveExecutionState.SUBMITTED
    assert submitted.broker_order_id == "broker-1"
    assert submitted.submitted_at == clock.value


def test_aborted_is_only_allowed_before_submission_pending(tmp_path):
    clock = Clock()
    journal = _journal(tmp_path, clock)
    _prepare(journal)
    clock.advance()

    aborted = journal.mark_aborted(
        "exec-key-1",
        detail="Boundary rejected before transport.",
    )
    assert aborted.state is LiveExecutionState.ABORTED

    with pytest.raises(LiveExecutionAlreadyClaimedError):
        journal.claim("exec-key-1")

    journal.prepare(
        "exec-key-2",
        order_fingerprint="fingerprint-2",
        order_id="order-2",
        signal_id="signal-2",
    )
    clock.advance()
    journal.claim("exec-key-2")
    clock.advance()
    journal.mark_submission_pending("exec-key-2")

    with pytest.raises(LiveExecutionTransitionError):
        journal.mark_aborted("exec-key-2")


def test_unknown_is_not_a_retryable_state(tmp_path):
    clock = Clock()
    journal = _journal(tmp_path, clock)
    _prepare(journal)
    clock.advance()
    journal.claim("exec-key-1")
    clock.advance()

    unknown = journal.mark_unknown("exec-key-1")
    assert unknown.state is LiveExecutionState.UNKNOWN
    assert unknown.state.is_terminal
    assert unknown.state.blocks_reclaim


def test_journal_has_no_broker_or_send_api(tmp_path):
    clock = Clock()
    journal = _journal(tmp_path, clock)

    forbidden = {
        "submit_order",
        "send_order",
        "sendorder",
        "transmit",
        "execute_live_order",
    }
    assert forbidden.isdisjoint(dir(journal))
