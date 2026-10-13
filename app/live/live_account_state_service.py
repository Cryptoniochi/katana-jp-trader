"""Authoritative kabu Station account state for the activated Live runtime.

This module is deliberately read-only.  It refreshes the broker snapshot from
kabu Station immediately before Live runtime decisions and exposes normalized
cash-position/order state.  A partial or failed broker snapshot is rejected so
Live execution can fail closed instead of falling back to PaperBroker state.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from app.live.kabu_station_read_only import (
    KabuStationReadOnlyReportWriter,
    KabuStationReadOnlyService,
    KabuStationReadOnlySnapshot,
)


class LiveAccountStateUnavailableError(RuntimeError):
    """Raised when a complete authoritative broker state cannot be obtained."""


@dataclass(frozen=True, slots=True)
class LiveCashPosition:
    """Normalized cash-equity position reported by kabu Station."""

    code: str
    quantity: int
    average_price: float
    current_price: float

    @property
    def market_value(self) -> float:
        return self.quantity * self.current_price


@dataclass(frozen=True, slots=True)
class LiveAccountState:
    """One complete, internally consistent broker read at a point in time."""

    generated_at: datetime
    cash_balance: float
    positions: tuple[LiveCashPosition, ...]
    orders: tuple[dict[str, object], ...]

    @property
    def position_codes(self) -> frozenset[str]:
        return frozenset(position.code for position in self.positions)

    @property
    def total_exposure(self) -> float:
        return sum(position.market_value for position in self.positions)

    @property
    def active_orders(self) -> tuple[dict[str, object], ...]:
        return tuple(
            order
            for order in self.orders
            if _integer(order.get("State"), "order State") in {1, 2, 3, 4}
        )


SnapshotProvider = Callable[[], KabuStationReadOnlySnapshot]


class KabuStationLiveAccountStateService:
    """Refresh and normalize the real kabu Station account state.

    The service never uses PaperBroker and never submits/cancels an order.
    ``refresh`` requires a complete snapshot.  Any missing wallet, partial
    endpoint result, malformed position, or non-finite numeric value raises
    ``LiveAccountStateUnavailableError`` so the caller can stop Live execution.
    """

    def __init__(
        self,
        *,
        read_only_service: KabuStationReadOnlyService,
        report_writer: KabuStationReadOnlyReportWriter | None = None,
    ) -> None:
        self.read_only_service = read_only_service
        self.report_writer = report_writer

    def refresh(self) -> LiveAccountState:
        snapshot = self.read_only_service.collect()
        if self.report_writer is not None:
            self.report_writer.write(snapshot)
        return self.from_snapshot(snapshot)

    @staticmethod
    def from_snapshot(snapshot: KabuStationReadOnlySnapshot) -> LiveAccountState:
        if snapshot.generated_at.tzinfo is None:
            raise LiveAccountStateUnavailableError(
                "Broker snapshot timestamp must be timezone-aware."
            )
        if (
            snapshot.state != "complete"
            or not snapshot.connected
            or not snapshot.token_issued
            or snapshot.errors
        ):
            raise LiveAccountStateUnavailableError(
                "Complete kabu Station account state is required for Live execution."
            )
        if snapshot.cash_wallet is None:
            raise LiveAccountStateUnavailableError(
                "Cash wallet is unavailable in the broker snapshot."
            )

        cash_balance = _cash_balance(snapshot.cash_wallet)
        positions = tuple(_position(row) for row in snapshot.positions)
        return LiveAccountState(
            generated_at=snapshot.generated_at.astimezone(timezone.utc),
            cash_balance=cash_balance,
            positions=positions,
            orders=tuple(dict(order) for order in snapshot.orders),
        )


def _cash_balance(wallet: dict[str, object]) -> float:
    # StockAccountWallet is the primary cash-equity wallet.  The AuKC value is
    # accepted only as a compatibility fallback for kabu Station variants that
    # omit the primary key.
    for key in ("StockAccountWallet", "AuKCStockAccountWallet"):
        if key in wallet and wallet.get(key) is not None:
            return _finite_non_negative(wallet.get(key), key)
    raise LiveAccountStateUnavailableError(
        "Cash wallet does not contain StockAccountWallet."
    )


def _position(row: dict[str, object]) -> LiveCashPosition:
    code = str(row.get("Symbol") or "").strip()
    if not code.isdigit() or len(code) not in {4, 5}:
        raise LiveAccountStateUnavailableError(
            f"Invalid broker position symbol: {code!r}"
        )

    quantity = _integer(row.get("LeavesQty", row.get("Qty")), "position quantity")
    if quantity <= 0:
        raise LiveAccountStateUnavailableError(
            f"Broker position quantity must be positive: code={code}"
        )

    average_price = _finite_non_negative(row.get("Price"), "position Price")
    current_raw = row.get("CurrentPrice")
    current_price = (
        average_price
        if current_raw is None
        else _finite_non_negative(current_raw, "position CurrentPrice")
    )
    if average_price <= 0 or current_price <= 0:
        raise LiveAccountStateUnavailableError(
            f"Broker position prices must be positive: code={code}"
        )

    return LiveCashPosition(
        code=code,
        quantity=quantity,
        average_price=average_price,
        current_price=current_price,
    )


def _finite_non_negative(value: object, label: str) -> float:
    if isinstance(value, bool):
        raise LiveAccountStateUnavailableError(f"{label} must be numeric.")
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise LiveAccountStateUnavailableError(f"{label} must be numeric.") from error
    if not math.isfinite(number) or number < 0:
        raise LiveAccountStateUnavailableError(
            f"{label} must be a finite non-negative number."
        )
    return number


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool):
        raise LiveAccountStateUnavailableError(f"{label} must be an integer.")
    try:
        number = int(value)
    except (TypeError, ValueError) as error:
        raise LiveAccountStateUnavailableError(f"{label} must be an integer.") from error
    return number
