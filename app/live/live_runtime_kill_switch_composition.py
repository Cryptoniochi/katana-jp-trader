"""Phase 6-C composition for a fail-closed live-runtime Kill Switch.

This module only composes read-only state providers.  It does not enable the
locked live runtime integration and it has no order-transmission capability.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

from app.live.live_runtime_kill_switch_state import (
    LiveRuntimeKillSwitchStateProvider,
)
from app.risk.kill_switch_models import KillSwitchSnapshot


BoolProvider = Callable[[], bool]
FloatProvider = Callable[[], float]
IntProvider = Callable[[], int]
NowProvider = Callable[[], datetime]


class LiveRuntimeKillSwitchComposition:
    """Build the Phase 6-C Kill Switch snapshot from real read-only sources.

    Manual blocking intentionally remains fail-closed until a reviewed manual
    control source is connected.  Passing ``manual_blocked_provider=None`` is
    therefore the safe Phase 6-C default.
    """

    def __init__(
        self,
        *,
        daily_profit_loss_provider: FloatProvider,
        consecutive_loss_count_provider: IntProvider,
        runtime_health_ok_provider: BoolProvider,
        heartbeat_alive_provider: BoolProvider,
        broker_available_provider: BoolProvider,
        manual_blocked_provider: BoolProvider | None = None,
        max_daily_loss: float = 50_000.0,
        max_consecutive_losses: int = 3,
        now_provider: NowProvider | None = None,
    ) -> None:
        self._provider = LiveRuntimeKillSwitchStateProvider(
            manual_blocked_provider=manual_blocked_provider,
            daily_profit_loss_provider=daily_profit_loss_provider,
            consecutive_loss_count_provider=(
                consecutive_loss_count_provider
            ),
            runtime_health_ok_provider=runtime_health_ok_provider,
            heartbeat_alive_provider=heartbeat_alive_provider,
            broker_available_provider=broker_available_provider,
            max_daily_loss=max_daily_loss,
            max_consecutive_losses=max_consecutive_losses,
            now_provider=now_provider,
        )

    def __call__(self) -> KillSwitchSnapshot:
        """Return a fresh snapshot; underlying providers are read on each call."""
        return self._provider()

    @property
    def state_provider(self) -> LiveRuntimeKillSwitchStateProvider:
        """Expose the composed provider for inspection/tests only."""
        return self._provider
