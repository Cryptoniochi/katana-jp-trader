"""Fail-closed Live position/protective-stop reconciliation guard."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.live.live_protective_exit_service import LiveProtectiveExitDecision
from app.live.live_protective_stop_repository import (
    LiveProtectiveStopState,
    SQLiteLiveProtectiveStopRepository,
)


@dataclass(frozen=True, slots=True)
class LivePositionProtectionReconciliationResult:
    evaluated_positions: int
    evaluated_stops: int
    retired_stale_stops: int
    blocked: int
    messages: tuple[str, ...]


class LivePositionProtectionReconciliation:
    """Require exactly matching durable protection for every actual Live position.

    This service never submits or cancels an order.  It obtains the authoritative
    position set through the existing EOD planning read boundary and compares it
    with durable current protective-stop rows.

    Missing protection, quantity mismatch, duplicate protection, or account-read
    failure blocks new risk.  A stale ACTIVE stop for an already-flat symbol is
    safe to retire.  EXIT_PENDING is also retired only after authoritative flat.
    """

    def __init__(
        self,
        *,
        repository: SQLiteLiveProtectiveStopRepository,
        exit_service,
    ) -> None:
        self.repository = repository
        self.exit_service = exit_service

    def __call__(self, trading_date: date) -> LivePositionProtectionReconciliationResult:
        messages: list[str] = []
        blocked = retired = 0

        batch = self.exit_service.plan_end_of_day(trading_date=trading_date)
        if batch.is_blocked:
            return LivePositionProtectionReconciliationResult(
                evaluated_positions=0,
                evaluated_stops=len(self.repository.list_current()),
                retired_stale_stops=0,
                blocked=1,
                messages=("Authoritative Live position snapshot is unavailable.",),
            )

        positions: dict[str, int] = {}
        for plan in batch.plans:
            if plan.decision is LiveProtectiveExitDecision.EXIT_REQUIRED:
                if plan.code is None or plan.quantity <= 0:
                    blocked += 1
                    messages.append("Authoritative Live position plan is malformed.")
                    continue
                positions[plan.code] = positions.get(plan.code, 0) + int(plan.quantity)

        stops = self.repository.list_current()
        by_code: dict[str, list] = {}
        for stop in stops:
            by_code.setdefault(stop.code, []).append(stop)

        # Every actual position must have exactly one current durable stop whose
        # protected quantity matches the authoritative broker quantity.
        for code, quantity in sorted(positions.items()):
            current = by_code.get(code, [])
            if len(current) != 1:
                blocked += 1
                messages.append(
                    f"{code}: actual Live position has {len(current)} current protective stops."
                )
                continue
            stop = current[0]
            if stop.quantity != quantity:
                blocked += 1
                messages.append(
                    f"{code}: protective quantity {stop.quantity} != Live quantity {quantity}."
                )

        # Durable stops with no actual position are stale.  Authoritative flat is
        # sufficient to retire them; this is persistence cleanup, never transport.
        for code, current in sorted(by_code.items()):
            if code in positions:
                continue
            for stop in current:
                self.repository.retire(entry_execution_key=stop.entry_execution_key)
                retired += 1
                messages.append(f"{code}: retired stale {stop.state.value} protective stop.")

        return LivePositionProtectionReconciliationResult(
            evaluated_positions=len(positions),
            evaluated_stops=len(stops),
            retired_stale_stops=retired,
            blocked=blocked,
            messages=tuple(messages),
        )
