"""Strict equity calculation from a saved kabu Station read-only snapshot."""

from __future__ import annotations

import math

from app.live.kabu_station_read_only import KabuStationReadOnlySnapshot


class KabuStationSavedEquityCalculator:
    """Calculate cash, exposure and equity without broker/network access."""

    def __call__(
        self,
        snapshot: KabuStationReadOnlySnapshot | None,
    ) -> tuple[float, float, float, frozenset[str]]:
        if snapshot is None:
            raise RuntimeError("Saved kabu Station snapshot is unavailable.")
        if (
            not snapshot.connected
            or not snapshot.token_issued
            or snapshot.state.strip().lower() != "complete"
            or snapshot.errors
        ):
            raise RuntimeError(
                "Saved kabu Station snapshot is not complete and healthy."
            )

        cash = self._required_number(
            snapshot.cash_wallet,
            ("StockAccountWallet",),
            "cash balance",
        )
        if cash < 0:
            raise RuntimeError("cash balance must be non-negative.")

        exposure = 0.0
        codes: set[str] = set()
        for position in snapshot.positions:
            if not isinstance(position, dict):
                raise RuntimeError("Broker position must be an object.")

            code = str(position.get("Symbol") or "").strip()
            if not code.isdigit() or len(code) not in {4, 5}:
                raise RuntimeError("Broker position has an invalid Symbol.")

            quantity = self._required_number(
                position,
                ("LeavesQty", "HoldQty"),
                f"position quantity for {code}",
            )
            price = self._required_number(
                position,
                ("CurrentPrice", "Price"),
                f"position price for {code}",
            )
            if quantity < 0 or price < 0:
                raise RuntimeError(
                    "Broker position values must be non-negative."
                )
            if quantity > 0:
                codes.add(code)
                exposure += quantity * price

        equity = cash + exposure
        if not math.isfinite(exposure) or not math.isfinite(equity):
            raise RuntimeError("Calculated live account values must be finite.")

        return cash, exposure, equity, frozenset(codes)

    @classmethod
    def _required_number(cls, payload, keys, label):
        if payload is None:
            raise RuntimeError(f"{label} source is unavailable.")
        present = [key for key in keys if key in payload]
        if not present:
            raise RuntimeError(f"{label} is unavailable.")
        values = [cls._finite(payload[key], label) for key in present]
        if any(value != values[0] for value in values[1:]):
            raise RuntimeError(f"{label} is ambiguous.")
        return values[0]

    @staticmethod
    def _finite(value, label):
        if isinstance(value, bool):
            raise RuntimeError(f"{label} must be numeric.")
        try:
            number = float(value)
        except (TypeError, ValueError) as error:
            raise RuntimeError(f"{label} must be numeric.") from error
        if not math.isfinite(number):
            raise RuntimeError(f"{label} must be finite.")
        return number
