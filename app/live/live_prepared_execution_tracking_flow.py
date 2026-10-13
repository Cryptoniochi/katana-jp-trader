"""Final Live pre-submit bridge: risk/safety preparation -> claim -> tracking.

This module contains no PaperBroker dependency.  It deliberately reuses the
locked live boundary for final risk/idempotency checks, then requires an atomic
CLAIMED journal state before the activated submission coordinator can run.
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

from app.live.live_execution_claim_models import LiveExecutionClaimDecision
from app.live.live_execution_tracking_flow import (
    LiveExecutionTrackingFlow,
    LiveExecutionTrackingResult,
)
from app.live.live_execution_preparation_service import (
    LockedLiveExecutionPreparationService,
)
from app.live.live_execution_claim_gate import LiveExecutionClaimGate
from app.live.live_order_models import LiveOrderIntent
from app.trading.order_models import TradeOrder

NowProvider = Callable[[], datetime]


class LivePreparedExecutionTrackingFlow:
    """Require durable PREPARED -> CLAIMED before live tracking/submission."""

    def __init__(
        self,
        *,
        preparation_service: LockedLiveExecutionPreparationService,
        claim_gate: LiveExecutionClaimGate,
        tracking_flow: LiveExecutionTrackingFlow,
        now_provider: NowProvider | None = None,
    ) -> None:
        self.preparation_service = preparation_service
        self.claim_gate = claim_gate
        self.tracking_flow = tracking_flow
        self.now_provider = now_provider or (lambda: datetime.now(timezone.utc))

    def submit(
        self,
        *,
        execution_key: str,
        order: TradeOrder,
        trading_date,
        required_baseline_quantity: int | None = None,
    ) -> LiveExecutionTrackingResult:
        now = self.now_provider()
        if now.tzinfo is None:
            raise ValueError("now_provider must return a timezone-aware datetime")
        intent = LiveOrderIntent(
            order=order,
            idempotency_key=execution_key,
            created_at=now,
        )
        prepared = self.preparation_service.prepare(intent)
        if not prepared.is_prepared:
            raise RuntimeError(
                "Live execution preparation was blocked; submission is prohibited."
            )
        claim = self.claim_gate.claim(execution_key)
        if claim.decision is not LiveExecutionClaimDecision.CLAIMED:
            raise RuntimeError(
                "Live execution claim was blocked; submission is prohibited."
            )
        return self.tracking_flow.submit(
            execution_key=execution_key,
            order=order,
            trading_date=trading_date,
            required_baseline_quantity=required_baseline_quantity,
        )

    def reconcile(
        self, *, execution_key: str, order: TradeOrder
    ) -> LiveExecutionTrackingResult:
        return self.tracking_flow.reconcile(
            execution_key=execution_key,
            order=order,
        )
