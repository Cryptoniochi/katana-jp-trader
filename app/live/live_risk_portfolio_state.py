"""Fail-closed mapping from saved kabu Station state to live risk portfolio."""
from __future__ import annotations
import math
from collections.abc import Callable
from datetime import datetime
from zoneinfo import ZoneInfo
from app.live.kabu_station_read_only import KabuStationReadOnlySnapshot
from app.live.risk_models import RiskPortfolioSnapshot

TOKYO = ZoneInfo("Asia/Tokyo")
SnapshotProvider = Callable[[], KabuStationReadOnlySnapshot | None]
FloatProvider = Callable[[], float]
IntProvider = Callable[[], int]
NowProvider = Callable[[], datetime]

class KabuStationRiskPortfolioProvider:
    """Build risk state from an already-saved broker snapshot; fail closed."""
    def __init__(self, *, snapshot_provider: SnapshotProvider,
                 daily_profit_loss_provider: FloatProvider,
                 consecutive_loss_count_provider: IntProvider,
                 peak_equity_provider: FloatProvider,
                 now_provider: NowProvider) -> None:
        self.snapshot_provider=snapshot_provider
        self.daily_profit_loss_provider=daily_profit_loss_provider
        self.consecutive_loss_count_provider=consecutive_loss_count_provider
        self.peak_equity_provider=peak_equity_provider
        self.now_provider=now_provider

    def __call__(self) -> RiskPortfolioSnapshot:
        snapshot=self.snapshot_provider()
        if snapshot is None:
            raise RuntimeError("Saved kabu Station snapshot is unavailable.")
        if (not snapshot.connected or not snapshot.token_issued
                or snapshot.state.strip().lower()!="complete" or snapshot.errors):
            raise RuntimeError("Saved kabu Station snapshot is not complete and healthy.")
        cash=self._required_number(snapshot.cash_wallet,("StockAccountWallet",),"cash balance")
        exposure=0.0; codes=set()
        for position in snapshot.positions:
            if not isinstance(position,dict):
                raise RuntimeError("Broker position must be an object.")
            code=str(position.get("Symbol") or "").strip()
            if not code.isdigit() or len(code) not in {4,5}:
                raise RuntimeError("Broker position has an invalid Symbol.")
            qty=self._required_number(position,("LeavesQty","HoldQty"),f"position quantity for {code}")
            price=self._required_number(position,("CurrentPrice","Price"),f"position price for {code}")
            if qty < 0 or price < 0:
                raise RuntimeError("Broker position values must be non-negative.")
            if qty > 0:
                codes.add(code); exposure += qty*price
        current_equity=cash+exposure
        peak=self._finite(self.peak_equity_provider(),"peak equity")
        daily=self._finite(self.daily_profit_loss_provider(),"daily realized profit/loss")
        losses=self.consecutive_loss_count_provider()
        if isinstance(losses,bool) or not isinstance(losses,int) or losses<0:
            raise RuntimeError("Consecutive loss count must be a non-negative integer.")
        now=self.now_provider()
        if now.tzinfo is None:
            raise RuntimeError("now_provider must return timezone-aware datetime.")
        peak=max(peak,current_equity)
        return RiskPortfolioSnapshot(
            trading_date=now.astimezone(TOKYO).date(), cash_balance=cash,
            total_exposure=exposure, current_equity=current_equity,
            peak_equity=peak, daily_realized_profit_loss=daily,
            consecutive_losses=losses, open_position_codes=frozenset(codes))

    @classmethod
    def _required_number(cls,payload,keys,label):
        if payload is None: raise RuntimeError(f"{label} source is unavailable.")
        present=[k for k in keys if k in payload]
        if not present: raise RuntimeError(f"{label} is unavailable.")
        values=[cls._finite(payload[k],label) for k in present]
        if any(v != values[0] for v in values[1:]):
            raise RuntimeError(f"{label} is ambiguous.")
        return values[0]

    @staticmethod
    def _finite(value,label):
        if isinstance(value,bool): raise RuntimeError(f"{label} must be numeric.")
        try: number=float(value)
        except (TypeError,ValueError) as e: raise RuntimeError(f"{label} must be numeric.") from e
        if not math.isfinite(number): raise RuntimeError(f"{label} must be finite.")
        if number < 0 and label in {"cash balance","peak equity"}:
            raise RuntimeError(f"{label} must be non-negative.")
        return number
