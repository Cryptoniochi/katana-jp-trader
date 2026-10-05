"""Phase 6-D Step 6A simulated Live broker transport.

This transport is intentionally incapable of network I/O.  It exists only to
prove that a validated LiveTransportRequest can reach the final transport shape
without enabling the real locked transport or sending an order.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import date, datetime, timezone

from app.live.execution_mode import (
    ExecutionModeSettings,
    LiveArmingPolicy,
)
from app.live.live_broker_transport_models import LiveTransportRequest
from app.live.live_transport_dry_run_models import (
    SimulatedLiveTransportDecision,
    SimulatedLiveTransportResult,
)


NowProvider = Callable[[], datetime]


class SimulatedLiveBrokerTransport:
    """Network-free transport simulator with normal daily Live authorization."""

    def __init__(
        self,
        *,
        execution_settings: ExecutionModeSettings,
        arming_policy: LiveArmingPolicy | None = None,
        now_provider: NowProvider | None = None,
    ) -> None:
        self.execution_settings = execution_settings
        self.arming_policy = arming_policy or LiveArmingPolicy()
        self.now_provider = now_provider or (lambda: datetime.now(timezone.utc))

    def evaluate(
        self,
        request: LiveTransportRequest,
        *,
        trading_date: date,
    ) -> SimulatedLiveTransportResult:
        """Authorize the dry-run and return a deterministic simulated receipt."""

        self.arming_policy.require_authorized(
            self.execution_settings,
            trading_date=trading_date,
        )
        evaluated_at = self._current_time()
        receipt_seed = (
            f"{request.execution_key}|{request.order.order_id}|"
            f"{request.order.signal_id}|{trading_date.isoformat()}"
        )
        receipt = hashlib.sha256(receipt_seed.encode("utf-8")).hexdigest()[:20]

        return SimulatedLiveTransportResult(
            request=request,
            decision=SimulatedLiveTransportDecision.SIMULATED_ACCEPTED,
            evaluated_at=evaluated_at,
            simulated_broker_order_id=f"DRYRUN-{receipt}",
            message=(
                "Dry-run transport accepted the request locally. "
                "No broker or network operation occurred."
            ),
        )

    def _current_time(self) -> datetime:
        current = self.now_provider()
        if current.tzinfo is None:
            raise ValueError("now_provider must return a timezone-aware datetime.")
        return current.astimezone(timezone.utc)
