"""Phase 6-C Step 1 locked live broker transport.

Safety invariants:
- the compile-time/default transport lock is False;
- runtime arming is independently required;
- the existing execution-mode daily arming policy is independently required;
- no BrokerAdapter is accepted;
- no kabu Station order endpoint exists here;
- no network client is accepted;
- every request terminates at LOCKED.

This is a transport *boundary*, not a transport implementation.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timezone

from app.live.execution_mode import (
    ExecutionModeSettings,
    LiveArmingPolicy,
    LiveTradingLockError,
)
from app.live.live_broker_transport_models import (
    LiveTransportDecision,
    LiveTransportLockReason,
    LiveTransportRequest,
    LiveTransportResult,
)


# Phase 6-C Step 1 compile-time/default lock.
# This must remain False until a later, explicitly reviewed transport phase.
LIVE_BROKER_TRANSPORT_ENABLED = False


NowProvider = Callable[[], datetime]


class LockedLiveBrokerTransport:
    """Live transport boundary that cannot transmit orders in Step 1."""

    def __init__(
        self,
        *,
        execution_settings: ExecutionModeSettings,
        arming_policy: LiveArmingPolicy | None = None,
        runtime_armed: bool = False,
        now_provider: NowProvider | None = None,
    ) -> None:
        self.execution_settings = execution_settings
        self.arming_policy = (
            arming_policy if arming_policy is not None else LiveArmingPolicy()
        )
        self.runtime_armed = bool(runtime_armed)
        self.now_provider = (
            now_provider
            if now_provider is not None
            else lambda: datetime.now(timezone.utc)
        )

    def evaluate(
        self,
        request: LiveTransportRequest,
        *,
        trading_date: date,
    ) -> LiveTransportResult:
        """Evaluate all locks and stop before any transport can exist."""

        evaluated_at = self._current_time()

        if not LIVE_BROKER_TRANSPORT_ENABLED:
            return self._locked(
                request,
                reason=LiveTransportLockReason.STATIC_LOCK,
                evaluated_at=evaluated_at,
                message=(
                    "Live broker transport is disabled by the "
                    "compile-time/default lock."
                ),
            )

        if not self.runtime_armed:
            return self._locked(
                request,
                reason=LiveTransportLockReason.RUNTIME_LOCK,
                evaluated_at=evaluated_at,
                message="Live broker transport runtime ARM is disabled.",
            )

        try:
            self.arming_policy.require_authorized(
                self.execution_settings,
                trading_date=trading_date,
            )
        except LiveTradingLockError as error:
            return self._locked(
                request,
                reason=LiveTransportLockReason.EXECUTION_MODE_LOCK,
                evaluated_at=evaluated_at,
                message=f"Execution mode authorization rejected: {error}",
            )

        # Defense in depth. Step 1 intentionally has no transport object,
        # broker adapter, HTTP client, or order endpoint to invoke.
        return self._locked(
            request,
            reason=LiveTransportLockReason.NO_TRANSPORT,
            evaluated_at=evaluated_at,
            message=(
                "Live broker transport is not implemented in Phase 6-C Step 1."
            ),
        )

    @staticmethod
    def _locked(
        request: LiveTransportRequest,
        *,
        reason: LiveTransportLockReason,
        evaluated_at: datetime,
        message: str,
    ) -> LiveTransportResult:
        return LiveTransportResult(
            request=request,
            decision=LiveTransportDecision.LOCKED,
            reason=reason,
            evaluated_at=evaluated_at,
            message=message,
        )

    def _current_time(self) -> datetime:
        current = self.now_provider()
        if current.tzinfo is None:
            raise ValueError("now_provider must return a timezone-aware datetime.")
        return current
