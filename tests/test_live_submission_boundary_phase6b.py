from datetime import datetime, timezone

import pytest

from app.live.live_execution_journal_models import LiveExecutionState
from app.live.live_execution_journal_repository import (
    LiveExecutionTransitionError,
    SQLiteLiveExecutionJournal,
)
from app.live.live_submission_boundary import LockedLiveSubmissionBoundary
from app.live.live_submission_boundary_models import (
    LiveSubmissionBoundaryDecision,
)


NOW = datetime(2026, 10, 3, 3, 0, 0, tzinfo=timezone.utc)
KEY = "execution-key-step4"


def _journal(tmp_path):
    return SQLiteLiveExecutionJournal(
        tmp_path / "katana.db",
        now_provider=lambda: NOW,
    )


def _prepare_and_claim(journal):
    journal.prepare(
        execution_key=KEY,
        order_fingerprint="fingerprint-step4",
        order_id="order-step4",
        signal_id="signal-step4",
    )
    return journal.claim(KEY)


def _boundary(journal):
    return LockedLiveSubmissionBoundary(
        journal=journal,
        now_provider=lambda: NOW,
    )


def test_claimed_execution_can_enter_submission_pending(tmp_path):
    journal = _journal(tmp_path)
    _prepare_and_claim(journal)

    result = _boundary(journal).enter_submission_pending(KEY)

    assert (
        result.decision
        is LiveSubmissionBoundaryDecision.SUBMISSION_PENDING
    )
    assert result.is_submission_pending is True
    assert result.journal_record.state is LiveExecutionState.SUBMISSION_PENDING
    assert journal.get_required(KEY).state is LiveExecutionState.SUBMISSION_PENDING


def test_prepared_execution_cannot_skip_claim(tmp_path):
    journal = _journal(tmp_path)
    journal.prepare(
        execution_key=KEY,
        order_fingerprint="fingerprint-step4",
        order_id="order-step4",
        signal_id="signal-step4",
    )

    with pytest.raises(LiveExecutionTransitionError):
        _boundary(journal).enter_submission_pending(KEY)

    assert journal.get_required(KEY).state is LiveExecutionState.PREPARED


def test_submission_pending_cannot_be_entered_twice(tmp_path):
    journal = _journal(tmp_path)
    _prepare_and_claim(journal)
    boundary = _boundary(journal)
    boundary.enter_submission_pending(KEY)

    with pytest.raises(LiveExecutionTransitionError):
        boundary.enter_submission_pending(KEY)


def test_recovered_submission_pending_is_frozen_unknown(tmp_path):
    path = tmp_path / "katana.db"
    journal = SQLiteLiveExecutionJournal(path, now_provider=lambda: NOW)
    _prepare_and_claim(journal)
    _boundary(journal).enter_submission_pending(KEY)

    reopened = SQLiteLiveExecutionJournal(path, now_provider=lambda: NOW)
    result = _boundary(reopened).recover_if_ambiguous(KEY)

    assert result is not None
    assert result.decision is LiveSubmissionBoundaryDecision.UNKNOWN
    assert result.is_unknown is True
    assert reopened.get_required(KEY).state is LiveExecutionState.UNKNOWN


def test_unknown_cannot_be_reclaimed_or_returned_to_pending(tmp_path):
    journal = _journal(tmp_path)
    _prepare_and_claim(journal)
    boundary = _boundary(journal)
    boundary.enter_submission_pending(KEY)
    boundary.freeze_pending_as_unknown(KEY)

    with pytest.raises(LiveExecutionTransitionError):
        boundary.enter_submission_pending(KEY)

    assert journal.get_required(KEY).state is LiveExecutionState.UNKNOWN


def test_recovery_leaves_claimed_execution_unchanged(tmp_path):
    journal = _journal(tmp_path)
    _prepare_and_claim(journal)

    result = _boundary(journal).recover_if_ambiguous(KEY)

    assert result is None
    assert journal.get_required(KEY).state is LiveExecutionState.CLAIMED


def test_recovery_leaves_prepared_execution_unchanged(tmp_path):
    journal = _journal(tmp_path)
    journal.prepare(
        execution_key=KEY,
        order_fingerprint="fingerprint-step4",
        order_id="order-step4",
        signal_id="signal-step4",
    )

    result = _boundary(journal).recover_if_ambiguous(KEY)

    assert result is None
    assert journal.get_required(KEY).state is LiveExecutionState.PREPARED


def test_freeze_requires_submission_pending(tmp_path):
    journal = _journal(tmp_path)
    _prepare_and_claim(journal)

    with pytest.raises(LiveExecutionTransitionError):
        _boundary(journal).freeze_pending_as_unknown(KEY)


def test_boundary_has_no_broker_or_send_api(tmp_path):
    boundary = _boundary(_journal(tmp_path))

    assert not hasattr(boundary, "submit")
    assert not hasattr(boundary, "submit_order")
    assert not hasattr(boundary, "send_order")
    assert not hasattr(boundary, "sendorder")
    assert not hasattr(boundary, "transmit")
    assert not hasattr(boundary, "broker")


def test_source_contains_no_broker_adapter_or_sendorder():
    from pathlib import Path

    source = Path(
        "app/live/live_submission_boundary.py"
    ).read_text(encoding="utf-8").lower()

    assert "brokeradapter" not in source
    assert "sendorder" not in source
    assert "submit_order(" not in source
