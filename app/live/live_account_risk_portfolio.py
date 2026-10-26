"""Fresh kabu Station account state mapped to Live risk and position views.

This module is read-only.  It deliberately bypasses PaperBroker: every call to
``KabuStationLiveRiskPortfolioProvider`` refreshes the real kabu Station account
before constructing the risk snapshot.  Broker-read failures therefore fail
closed instead of falling back to simulated state.
"""
from __future__ import annotations

import math
from collections.abc import Callable
from datetime import datetime
from zoneinfo import ZoneInfo

from app.live.live_account_state_service import (
    KabuStationLiveAccountStateService,
    LiveCashPosition,
)
from app.live.risk_models import RiskPortfolioSnapshot


TOKYO = ZoneInfo("Asia/Tokyo")
FloatProvider = Callable[[], float]
PeakEquityObserver = Callable[[float], float]
IntProvider = Callable[[], int]
NowProvider = Callable[[], datetime]


class KabuStationLiveRiskPortfolioProvider:
    """Build risk state from a freshly-read real broker account."""

    def __init__(
        self,
        *,
        account_state_service: KabuStationLiveAccountStateService,
        daily_profit_loss_provider: FloatProvider,
        consecutive_loss_count_provider: IntProvider,
        peak_equity_provider: FloatProvider,
        peak_equity_observer: PeakEquityObserver | None = None,
        now_provider: NowProvider,
    ) -> None:
        self.account_state_service = account_state_service
        self.daily_profit_loss_provider = daily_profit_loss_provider
        self.consecutive_loss_count_provider = consecutive_loss_count_provider
        self.peak_equity_provider = peak_equity_provider
        self.peak_equity_observer = peak_equity_observer
        self.now_provider = now_provider

    def __call__(self) -> RiskPortfolioSnapshot:
        state = self.account_state_service.refresh()
        current_equity = state.cash_balance + state.total_exposure
        saved_peak_equity = self._finite_non_negative(
            self.peak_equity_provider(), "peak equity"
        )
        peak_equity = max(saved_peak_equity, current_equity)
        if self.peak_equity_observer is not None and current_equity > saved_peak_equity:
            peak_equity = self._finite_non_negative(
                self.peak_equity_observer(current_equity), "observed peak equity"
            )
        daily_profit_loss = self._finite(
            self.daily_profit_loss_provider(), "daily realized profit/loss"
        )
        consecutive_losses = self.consecutive_loss_count_provider()
        if (
            isinstance(consecutive_losses, bool)
            or not isinstance(consecutive_losses, int)
            or consecutive_losses < 0
        ):
            raise RuntimeError(
                "Consecutive loss count must be a non-negative integer."
            )

        now = self.now_provider()
        if now.tzinfo is None:
            raise RuntimeError("now_provider must return timezone-aware datetime.")

        return RiskPortfolioSnapshot(
            trading_date=now.astimezone(TOKYO).date(),
            cash_balance=state.cash_balance,
            total_exposure=state.total_exposure,
            current_equity=current_equity,
            peak_equity=peak_equity,
            daily_realized_profit_loss=daily_profit_loss,
            consecutive_losses=consecutive_losses,
            open_position_codes=state.position_codes,
        )

    @staticmethod
    def _finite(value: object, label: str) -> float:
        if isinstance(value, bool):
            raise RuntimeError(f"{label} must be numeric.")
        try:
            number = float(value)
        except (TypeError, ValueError) as error:
            raise RuntimeError(f"{label} must be numeric.") from error
        if not math.isfinite(number):
            raise RuntimeError(f"{label} must be finite.")
        return number

    @classmethod
    def _finite_non_negative(cls, value: object, label: str) -> float:
        number = cls._finite(value, label)
        if number < 0:
            raise RuntimeError(f"{label} must be non-negative.")
        return number


class KabuStationLivePositionProvider:
    """Return real cash positions, never PaperBroker positions."""

    def __init__(
        self,
        *,
        account_state_service: KabuStationLiveAccountStateService,
    ) -> None:
        self.account_state_service = account_state_service

    def __call__(self) -> tuple[LiveCashPosition, ...]:
        return self.account_state_service.refresh().positions
