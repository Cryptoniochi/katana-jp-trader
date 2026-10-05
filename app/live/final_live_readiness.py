"""Phase 6-D Step 5 final Live activation-readiness gate.

Evaluates existing read-only safety inputs only. It does not enable runtime
integration, broker transport, or live order submission.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import StrEnum

from app.live.execution_mode import ExecutionModeSettings, LiveArmingPolicy, LiveTradingLockError
from app.live.live_order_safety import LiveOrderSafetySnapshot
from app.live.risk_models import RiskPortfolioSnapshot
from app.risk.kill_switch_models import KillSwitchSnapshot

BoolProvider = Callable[[], bool]
FloatProvider = Callable[[], float]
IntProvider = Callable[[], int]
PortfolioProvider = Callable[[], RiskPortfolioSnapshot]
SafetySnapshotProvider = Callable[[], LiveOrderSafetySnapshot]
KillSwitchSnapshotProvider = Callable[[], KillSwitchSnapshot]
NowProvider = Callable[[], datetime]


class FinalLiveReadinessState(StrEnum):
    BLOCKED = "blocked"
    ACTIVATION_READY = "activation_ready"


@dataclass(frozen=True, slots=True)
class FinalLiveReadinessItem:
    key: str
    passed: bool
    message: str


@dataclass(frozen=True, slots=True)
class FinalLiveReadinessReport:
    generated_at: datetime
    trading_date: date
    activation_ready: bool
    transport_ready: bool
    live_order_ready: bool
    state: FinalLiveReadinessState
    items: tuple[FinalLiveReadinessItem, ...]

    def __post_init__(self) -> None:
        if self.generated_at.tzinfo is None:
            raise ValueError("generated_at must be timezone-aware.")
        if self.transport_ready:
            raise ValueError("Phase 6-D transport_ready must remain False.")
        if self.live_order_ready:
            raise ValueError("Phase 6-D live_order_ready must remain False.")


class FinalLiveReadinessGate:
    """Aggregate existing safety truth without activating Live execution."""

    def __init__(
        self,
        *,
        manual_blocked_provider: BoolProvider,
        daily_profit_loss_provider: FloatProvider,
        consecutive_loss_count_provider: IntProvider,
        runtime_health_ok_provider: BoolProvider,
        heartbeat_alive_provider: BoolProvider,
        broker_available_provider: BoolProvider,
        portfolio_provider: PortfolioProvider,
        safety_snapshot_provider: SafetySnapshotProvider,
        kill_switch_snapshot_provider: KillSwitchSnapshotProvider,
        max_daily_loss: float = 50_000.0,
        max_consecutive_losses: int = 3,
        now_provider: NowProvider | None = None,
    ) -> None:
        if max_daily_loss <= 0:
            raise ValueError("max_daily_loss must be greater than zero.")
        if max_consecutive_losses <= 0:
            raise ValueError("max_consecutive_losses must be greater than zero.")
        self.manual_blocked_provider = manual_blocked_provider
        self.daily_profit_loss_provider = daily_profit_loss_provider
        self.consecutive_loss_count_provider = consecutive_loss_count_provider
        self.runtime_health_ok_provider = runtime_health_ok_provider
        self.heartbeat_alive_provider = heartbeat_alive_provider
        self.broker_available_provider = broker_available_provider
        self.portfolio_provider = portfolio_provider
        self.safety_snapshot_provider = safety_snapshot_provider
        self.kill_switch_snapshot_provider = kill_switch_snapshot_provider
        self.max_daily_loss = float(max_daily_loss)
        self.max_consecutive_losses = int(max_consecutive_losses)
        self.now_provider = now_provider or (lambda: datetime.now(timezone.utc))

    def check(self, *, execution_settings: ExecutionModeSettings, trading_date: date) -> FinalLiveReadinessReport:
        items = (
            self._check("manual_kill_switch", self._manual_clear),
            self._check("daily_loss", self._daily_loss_clear),
            self._check("consecutive_losses", self._consecutive_losses_clear),
            self._check("runtime_health", self.runtime_health_ok_provider),
            self._check("heartbeat", self.heartbeat_alive_provider),
            self._check("broker_availability", self.broker_available_provider),
            self._check("portfolio_state", self._portfolio_available),
            self._check("reconciliation_fault_tolerance", self._safety_clear),
            self._check("kill_switch", self._kill_switch_clear),
            self._execution_mode_item(execution_settings, trading_date),
        )
        activation_ready = all(item.passed for item in items)
        return FinalLiveReadinessReport(
            generated_at=self._now(),
            trading_date=trading_date,
            activation_ready=activation_ready,
            transport_ready=False,
            live_order_ready=False,
            state=FinalLiveReadinessState.ACTIVATION_READY if activation_ready else FinalLiveReadinessState.BLOCKED,
            items=items,
        )

    def _manual_clear(self) -> bool:
        return not bool(self.manual_blocked_provider())

    def _daily_loss_clear(self) -> bool:
        return float(self.daily_profit_loss_provider()) > -self.max_daily_loss

    def _consecutive_losses_clear(self) -> bool:
        return int(self.consecutive_loss_count_provider()) < self.max_consecutive_losses

    def _portfolio_available(self) -> bool:
        return self.portfolio_provider() is not None

    def _safety_clear(self) -> bool:
        return not self.safety_snapshot_provider().is_blocked

    def _kill_switch_clear(self) -> bool:
        snapshot = self.kill_switch_snapshot_provider()
        return (
            not snapshot.manual_blocked
            and not snapshot.daily_loss_blocked
            and not snapshot.consecutive_loss_blocked
            and snapshot.runtime_health_ok
            and snapshot.heartbeat_alive
            and snapshot.broker_available
        )

    @staticmethod
    def _execution_mode_item(settings: ExecutionModeSettings, trading_date: date) -> FinalLiveReadinessItem:
        try:
            LiveArmingPolicy().require_authorized(settings, trading_date=trading_date)
        except LiveTradingLockError as error:
            return FinalLiveReadinessItem("execution_mode_authorization", False, str(error))
        return FinalLiveReadinessItem(
            "execution_mode_authorization", True, "Daily Live execution-mode authorization is valid."
        )

    @staticmethod
    def _check(key: str, provider: Callable[[], bool]) -> FinalLiveReadinessItem:
        try:
            passed = bool(provider())
        except Exception as error:
            return FinalLiveReadinessItem(
                key, False, f"Unavailable or invalid: {type(error).__name__}: {error}"
            )
        return FinalLiveReadinessItem(key, passed, "ready" if passed else "blocked")

    def _now(self) -> datetime:
        current = self.now_provider()
        if current.tzinfo is None:
            raise ValueError("now_provider must return a timezone-aware datetime.")
        return current.astimezone(timezone.utc)
