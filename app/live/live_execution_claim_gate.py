"""Fail-closed Phase 6-B gate for PREPARED -> CLAIMED.

The service re-reads emergency safety and Kill Switch state immediately before
the journal's atomic claim operation.  Missing providers and provider failures
block ownership acquisition.  A blocked execution remains PREPARED so a later
healthy evaluation can retry safely.

This module deliberately contains no BrokerAdapter, HTTP client, sendorder,
submission-pending transition, or order transmission operation.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

from app.live.live_execution_claim_models import (
    LiveExecutionClaimBlockReason,
    LiveExecutionClaimDecision,
    LiveExecutionClaimResult,
)
from app.live.live_execution_journal_repository import (
    SQLiteLiveExecutionJournal,
)
from app.live.live_order_safety import LiveOrderSafetySnapshot
from app.risk.kill_switch_models import KillSwitchSnapshot
from app.risk.kill_switch_service import KillSwitchService


SafetySnapshotProvider = Callable[[], LiveOrderSafetySnapshot]
KillSwitchSnapshotProvider = Callable[[], KillSwitchSnapshot]
NowProvider = Callable[[], datetime]


class LiveExecutionClaimGate:
    """Acquire one PREPARED execution only after fresh fail-closed checks."""

    def __init__(
        self,
        *,
        journal: SQLiteLiveExecutionJournal,
        kill_switch_service: KillSwitchService,
        safety_snapshot_provider: SafetySnapshotProvider | None,
        kill_switch_snapshot_provider: KillSwitchSnapshotProvider | None,
        now_provider: NowProvider | None = None,
    ) -> None:
        self.journal = journal
        self.kill_switch_service = kill_switch_service
        self.safety_snapshot_provider = safety_snapshot_provider
        self.kill_switch_snapshot_provider = kill_switch_snapshot_provider
        self.now_provider = (
            now_provider
            if now_provider is not None
            else lambda: datetime.now(timezone.utc)
        )

    def claim(self, execution_key: str) -> LiveExecutionClaimResult:
        """Revalidate emergency state, then atomically PREPARED -> CLAIMED."""

        evaluated_at = self._current_time()
        prepared = self.journal.get_required(execution_key)

        if self.safety_snapshot_provider is None:
            return self._blocked(
                prepared,
                evaluated_at=evaluated_at,
                reason=LiveExecutionClaimBlockReason.SAFETY_STATE_UNAVAILABLE,
                message="Live execution claim blocked: safety provider unavailable.",
            )

        try:
            safety = self.safety_snapshot_provider()
        except Exception:
            return self._blocked(
                prepared,
                evaluated_at=evaluated_at,
                reason=LiveExecutionClaimBlockReason.SAFETY_STATE_UNAVAILABLE,
                message="Live execution claim blocked: safety state unavailable.",
            )

        if safety.safe_stop_active:
            return self._blocked(
                prepared,
                evaluated_at=evaluated_at,
                reason=LiveExecutionClaimBlockReason.SAFE_STOP,
                safety_snapshot=safety,
                message="Live execution claim blocked by Safe Stop.",
            )

        if not safety.reconciliation_consistent:
            return self._blocked(
                prepared,
                evaluated_at=evaluated_at,
                reason=LiveExecutionClaimBlockReason.RECONCILIATION,
                safety_snapshot=safety,
                message=(
                    "Live execution claim blocked by reconciliation state: "
                    f"{safety.reconciliation_state}"
                ),
            )

        if self.kill_switch_snapshot_provider is None:
            return self._blocked(
                prepared,
                evaluated_at=evaluated_at,
                reason=(
                    LiveExecutionClaimBlockReason.KILL_SWITCH_STATE_UNAVAILABLE
                ),
                safety_snapshot=safety,
                message=(
                    "Live execution claim blocked: Kill Switch provider "
                    "unavailable."
                ),
            )

        try:
            kill_evaluation = self.kill_switch_service.evaluate(
                self.kill_switch_snapshot_provider()
            )
        except Exception:
            return self._blocked(
                prepared,
                evaluated_at=evaluated_at,
                reason=(
                    LiveExecutionClaimBlockReason.KILL_SWITCH_STATE_UNAVAILABLE
                ),
                safety_snapshot=safety,
                message=(
                    "Live execution claim blocked: Kill Switch state "
                    "unavailable."
                ),
            )

        if kill_evaluation.is_blocked:
            return self._blocked(
                prepared,
                evaluated_at=evaluated_at,
                reason=LiveExecutionClaimBlockReason.KILL_SWITCH,
                safety_snapshot=safety,
                kill_switch_evaluation=kill_evaluation,
                message=(
                    "Live execution claim blocked by Kill Switch: "
                    f"{kill_evaluation.reason.value}"
                ),
            )

        claimed = self.journal.claim(execution_key)
        return LiveExecutionClaimResult(
            decision=LiveExecutionClaimDecision.CLAIMED,
            evaluated_at=evaluated_at,
            journal_record=claimed,
            safety_snapshot=safety,
            kill_switch_evaluation=kill_evaluation,
            message="Live execution ownership claimed; submission remains locked.",
        )

    @staticmethod
    def _blocked(
        record,
        *,
        evaluated_at,
        reason,
        message,
        safety_snapshot=None,
        kill_switch_evaluation=None,
    ) -> LiveExecutionClaimResult:
        return LiveExecutionClaimResult(
            decision=LiveExecutionClaimDecision.BLOCKED,
            evaluated_at=evaluated_at,
            journal_record=record,
            block_reason=reason,
            safety_snapshot=safety_snapshot,
            kill_switch_evaluation=kill_switch_evaluation,
            message=message,
        )

    def _current_time(self) -> datetime:
        current = self.now_provider()
        if current.tzinfo is None:
            raise ValueError("now_provider must return a timezone-aware datetime.")
        return current.astimezone(timezone.utc)
