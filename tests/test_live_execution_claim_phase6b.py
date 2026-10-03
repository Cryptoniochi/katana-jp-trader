from datetime import datetime, timezone

import pytest

from app.live.live_execution_claim_gate import LiveExecutionClaimGate
from app.live.live_execution_claim_models import (
    LiveExecutionClaimBlockReason,
    LiveExecutionClaimDecision,
)
from app.live.live_execution_journal_models import LiveExecutionState
from app.live.live_execution_journal_repository import (
    LiveExecutionAlreadyClaimedError,
    SQLiteLiveExecutionJournal,
)
from app.live.live_order_safety import LiveOrderSafetySnapshot
from app.risk.kill_switch_models import KillSwitchSnapshot
from app.risk.kill_switch_service import KillSwitchService


NOW = datetime(2026, 10, 3, 2, 0, 0, tzinfo=timezone.utc)
KEY = "execution-key-1"


def _journal(tmp_path):
    journal = SQLiteLiveExecutionJournal(
        tmp_path / "katana.db",
        now_provider=lambda: NOW,
    )
    journal.prepare(
        execution_key=KEY,
        order_fingerprint="fingerprint-1",
        order_id="order-1",
        signal_id="signal-1",
    )
    return journal


def _safety(*, safe_stop=False, consistent=True, state="consistent"):
    return LiveOrderSafetySnapshot(
        safe_stop_active=safe_stop,
        reconciliation_consistent=consistent,
        reconciliation_state=state,
        evaluated_at=NOW,
    )


def _kill(*, manual_blocked=False):
    return KillSwitchSnapshot(
        manual_blocked=manual_blocked,
        daily_loss_blocked=False,
        consecutive_loss_blocked=False,
        runtime_health_ok=True,
        heartbeat_alive=True,
        broker_available=True,
        evaluated_at=NOW,
    )


def _gate(
    journal,
    *,
    safety_provider=lambda: _safety(),
    kill_provider=lambda: _kill(),
):
    return LiveExecutionClaimGate(
        journal=journal,
        kill_switch_service=KillSwitchService(),
        safety_snapshot_provider=safety_provider,
        kill_switch_snapshot_provider=kill_provider,
        now_provider=lambda: NOW,
    )


def test_healthy_fresh_state_atomically_claims_prepared_execution(tmp_path):
    journal = _journal(tmp_path)

    result = _gate(journal).claim(KEY)

    assert result.decision is LiveExecutionClaimDecision.CLAIMED
    assert result.is_claimed is True
    assert result.block_reason is None
    assert result.journal_record.state is LiveExecutionState.CLAIMED
    assert journal.get_required(KEY).state is LiveExecutionState.CLAIMED


def test_missing_safety_provider_fails_closed_and_stays_prepared(tmp_path):
    journal = _journal(tmp_path)

    result = _gate(journal, safety_provider=None).claim(KEY)

    assert result.is_blocked is True
    assert (
        result.block_reason
        is LiveExecutionClaimBlockReason.SAFETY_STATE_UNAVAILABLE
    )
    assert journal.get_required(KEY).state is LiveExecutionState.PREPARED


def test_safety_provider_exception_fails_closed_and_stays_prepared(tmp_path):
    journal = _journal(tmp_path)

    def broken():
        raise RuntimeError("unavailable")

    result = _gate(journal, safety_provider=broken).claim(KEY)

    assert (
        result.block_reason
        is LiveExecutionClaimBlockReason.SAFETY_STATE_UNAVAILABLE
    )
    assert journal.get_required(KEY).state is LiveExecutionState.PREPARED


def test_safe_stop_blocks_claim_and_stays_prepared(tmp_path):
    journal = _journal(tmp_path)

    result = _gate(
        journal,
        safety_provider=lambda: _safety(safe_stop=True),
    ).claim(KEY)

    assert result.block_reason is LiveExecutionClaimBlockReason.SAFE_STOP
    assert journal.get_required(KEY).state is LiveExecutionState.PREPARED


def test_reconciliation_abnormality_blocks_claim_and_stays_prepared(tmp_path):
    journal = _journal(tmp_path)

    result = _gate(
        journal,
        safety_provider=lambda: _safety(
            consistent=False,
            state="mismatch",
        ),
    ).claim(KEY)

    assert result.block_reason is LiveExecutionClaimBlockReason.RECONCILIATION
    assert journal.get_required(KEY).state is LiveExecutionState.PREPARED


def test_missing_kill_switch_provider_fails_closed(tmp_path):
    journal = _journal(tmp_path)

    result = _gate(journal, kill_provider=None).claim(KEY)

    assert (
        result.block_reason
        is LiveExecutionClaimBlockReason.KILL_SWITCH_STATE_UNAVAILABLE
    )
    assert journal.get_required(KEY).state is LiveExecutionState.PREPARED


def test_kill_switch_provider_exception_fails_closed(tmp_path):
    journal = _journal(tmp_path)

    def broken():
        raise RuntimeError("unavailable")

    result = _gate(journal, kill_provider=broken).claim(KEY)

    assert (
        result.block_reason
        is LiveExecutionClaimBlockReason.KILL_SWITCH_STATE_UNAVAILABLE
    )
    assert journal.get_required(KEY).state is LiveExecutionState.PREPARED


def test_blocked_kill_switch_prevents_claim(tmp_path):
    journal = _journal(tmp_path)

    result = _gate(
        journal,
        kill_provider=lambda: _kill(manual_blocked=True),
    ).claim(KEY)

    assert result.block_reason is LiveExecutionClaimBlockReason.KILL_SWITCH
    assert journal.get_required(KEY).state is LiveExecutionState.PREPARED


def test_second_claim_is_rejected_by_durable_journal(tmp_path):
    journal = _journal(tmp_path)
    gate = _gate(journal)

    gate.claim(KEY)

    with pytest.raises(LiveExecutionAlreadyClaimedError):
        gate.claim(KEY)


def test_claim_survives_restart_and_cannot_be_reclaimed(tmp_path):
    path = tmp_path / "katana.db"
    first = SQLiteLiveExecutionJournal(path, now_provider=lambda: NOW)
    first.prepare(
        execution_key=KEY,
        order_fingerprint="fingerprint-1",
        order_id="order-1",
        signal_id="signal-1",
    )
    _gate(first).claim(KEY)

    reopened = SQLiteLiveExecutionJournal(path, now_provider=lambda: NOW)

    with pytest.raises(LiveExecutionAlreadyClaimedError):
        _gate(reopened).claim(KEY)


def test_claim_gate_has_no_submission_or_transport_api(tmp_path):
    gate = _gate(_journal(tmp_path))

    assert not hasattr(gate, "mark_submission_pending")
    assert not hasattr(gate, "submit")
    assert not hasattr(gate, "submit_order")
    assert not hasattr(gate, "send_order")
    assert not hasattr(gate, "sendorder")
    assert not hasattr(gate, "transmit")
