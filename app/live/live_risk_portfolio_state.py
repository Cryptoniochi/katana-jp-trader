"""Fail-closed mapping from saved kabu Station state to live risk portfolio."""

from __future__ import annotations

import math
from collections.abc import Callable
from datetime import datetime
from zoneinfo import ZoneInfo

from app.live.kabu_station_read_only import KabuStationReadOnlySnapshot
from app.live.live_saved_equity import KabuStationSavedEquityCalculator
from app.live.risk_models import RiskPortfolioSnapshot


TOKYO = ZoneInfo("Asia/Tokyo")
SnapshotProvider = Callable[[], KabuStationReadOnlySnapshot | None]
FloatProvider = Callable[[], float]
IntProvider = Callable[[], int]
NowProvider = Callable[[], datetime]


class KabuStationRiskPortfolioProvider:
    """Build risk state from an already-saved broker snapshot; fail closed."""

    def __init__(
        self,
        *,
        snapshot_provider: SnapshotProvider,
        daily_profit_loss_provider: FloatProvider,
        consecutive_loss_count_provider: IntProvider,
        peak_equity_provider: FloatProvider,
        now_provider: NowProvider,
        calculator: KabuStationSavedEquityCalculator | None = None,
    ) -> None:
        self.snapshot_provider = snapshot_provider
        self.daily_profit_loss_provider = daily_profit_loss_provider
        self.consecutive_loss_count_provider = consecutive_loss_count_provider
        self.peak_equity_provider = peak_equity_provider
        self.now_provider = now_provider
        self.calculator = calculator or KabuStationSavedEquityCalculator()

    def __call__(self) -> RiskPortfolioSnapshot:
        cash, exposure, current_equity, codes = self.calculator(
            self.snapshot_provider()
        )
        peak = self._finite(
            self.peak_equity_provider(),
            "peak equity",
            non_negative=True,
        )
        daily = self._finite(
            self.daily_profit_loss_provider(),
            "daily realized profit/loss",
        )
        losses = self.consecutive_loss_count_provider()
        if isinstance(losses, bool) or not isinstance(losses, int) or losses < 0:
            raise RuntimeError(
                "Consecutive loss count must be a non-negative integer."
            )

        now = self.now_provider()
        if now.tzinfo is None:
            raise RuntimeError(
                "now_provider must return timezone-aware datetime."
            )

        # A persisted peak may lag a newly observed higher current equity.
        # Never manufacture drawdown from that lag.
        peak = max(peak, current_equity)

        return RiskPortfolioSnapshot(
            trading_date=now.astimezone(TOKYO).date(),
            cash_balance=cash,
            total_exposure=exposure,
            current_equity=current_equity,
            peak_equity=peak,
            daily_realized_profit_loss=daily,
            consecutive_losses=losses,
            open_position_codes=codes,
        )

    @staticmethod
    def _finite(
        value: object,
        label: str,
        *,
        non_negative: bool = False,
    ) -> float:
        if isinstance(value, bool):
            raise RuntimeError(f"{label} must be numeric.")
        try:
            number = float(value)
        except (TypeError, ValueError) as error:
            raise RuntimeError(f"{label} must be numeric.") from error
        if not math.isfinite(number):
            raise RuntimeError(f"{label} must be finite.")
        if non_negative and number < 0:
            raise RuntimeError(f"{label} must be non-negative.")
        return number
