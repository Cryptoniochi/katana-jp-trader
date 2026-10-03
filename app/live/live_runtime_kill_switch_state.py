"""実Runtime状態からLive Kill Switch Snapshotをfail-closedで構築する。"""

from __future__ import annotations

import math
from collections.abc import Callable
from datetime import datetime, timezone

from app.risk.kill_switch_models import KillSwitchSnapshot


BoolProvider = Callable[[], bool]
FloatProvider = Callable[[], float]
IntProvider = Callable[[], int]
NowProvider = Callable[[], datetime]


class LiveRuntimeKillSwitchStateProvider:
    """Live境界用Kill Switch状態を実データだけから構築する。"""

    def __init__(
        self,
        *,
        manual_blocked_provider: BoolProvider | None = None,
        daily_profit_loss_provider: FloatProvider | None = None,
        consecutive_loss_count_provider: IntProvider | None = None,
        runtime_health_ok_provider: BoolProvider | None = None,
        heartbeat_alive_provider: BoolProvider | None = None,
        broker_available_provider: BoolProvider | None = None,
        max_daily_loss: float = 50_000.0,
        max_consecutive_losses: int = 3,
        now_provider: NowProvider | None = None,
    ) -> None:
        if max_daily_loss < 0:
            raise ValueError("日次損失上限は0以上である必要があります。")
        if max_consecutive_losses <= 0:
            raise ValueError("連敗上限は1以上である必要があります。")
        self.manual_blocked_provider = manual_blocked_provider
        self.daily_profit_loss_provider = daily_profit_loss_provider
        self.consecutive_loss_count_provider = consecutive_loss_count_provider
        self.runtime_health_ok_provider = runtime_health_ok_provider
        self.heartbeat_alive_provider = heartbeat_alive_provider
        self.broker_available_provider = broker_available_provider
        self.max_daily_loss = float(max_daily_loss)
        self.max_consecutive_losses = int(max_consecutive_losses)
        self.now_provider = now_provider or (lambda: datetime.now(timezone.utc))

    def __call__(self) -> KillSwitchSnapshot:
        return KillSwitchSnapshot(
            manual_blocked=self._blocked_when_unknown(
                self.manual_blocked_provider
            ),
            daily_loss_blocked=self._daily_loss_blocked(),
            consecutive_loss_blocked=self._consecutive_loss_blocked(),
            runtime_health_ok=self._false_when_unknown(
                self.runtime_health_ok_provider
            ),
            heartbeat_alive=self._false_when_unknown(
                self.heartbeat_alive_provider
            ),
            broker_available=self._false_when_unknown(
                self.broker_available_provider
            ),
            evaluated_at=self._now(),
        )

    def _daily_loss_blocked(self) -> bool:
        provider = self.daily_profit_loss_provider
        if provider is None:
            return True
        try:
            value = float(provider())
        except Exception:
            return True
        if not math.isfinite(value):
            return True
        return value <= -self.max_daily_loss

    def _consecutive_loss_blocked(self) -> bool:
        provider = self.consecutive_loss_count_provider
        if provider is None:
            return True
        try:
            raw_value = provider()
            if isinstance(raw_value, bool):
                return True
            value = int(raw_value)
        except Exception:
            return True
        if value < 0:
            return True
        return value >= self.max_consecutive_losses

    @staticmethod
    def _blocked_when_unknown(provider: BoolProvider | None) -> bool:
        if provider is None:
            return True
        try:
            value = provider()
        except Exception:
            return True
        if not isinstance(value, bool):
            return True
        return value

    @staticmethod
    def _false_when_unknown(provider: BoolProvider | None) -> bool:
        if provider is None:
            return False
        try:
            value = provider()
        except Exception:
            return False
        if not isinstance(value, bool):
            return False
        return value

    def _now(self) -> datetime:
        current = self.now_provider()
        if current.tzinfo is None:
            raise ValueError("現在日時にはタイムゾーンが必要です。")
        return current.astimezone(timezone.utc)
