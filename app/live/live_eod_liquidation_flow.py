"""Ownership-bounded Live EOD liquidation with authoritative verification."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from app.live.live_protective_exit_conflict_resolver import (
    LiveProtectiveExitConflictResolver,
)
from app.live.live_protective_exit_execution_flow import (
    LiveProtectiveExitExecutionDecision,
    LiveProtectiveExitExecutionFlow,
    LiveProtectiveExitExecutionResult,
)
from app.live.live_protective_exit_service import LiveProtectiveExitService
from app.live.live_protective_stop_repository import LiveProtectiveStopRecord


class LiveEodOwnershipRepository(Protocol):
    """Durable source proving which live positions belong to KATANA."""

    def list_current(self) -> tuple[LiveProtectiveStopRecord, ...]: ...


class LiveEodExecutionDecision(StrEnum):
    COMPLETE = "complete"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class LiveEodExecutionResult:
    decision: LiveEodExecutionDecision
    results: tuple[LiveProtectiveExitExecutionResult, ...]
    message: str


class LiveEodLiquidationFlow:
    """Liquidate only positions whose KATANA ownership is durably proven.

    The authoritative broker account may contain unrelated/manual holdings.  Those
    holdings are never submitted by this flow and do not prevent COMPLETE.

    A current durable protective-stop row is the ownership record.  Before any
    SELL is submitted, the broker-visible quantity for that symbol must exactly
    equal the durable owned quantity.  Missing, duplicate or quantity-mismatched
    ownership fails closed.

    COMPLETE means a fresh authoritative read contains no remaining position that
    matches a current KATANA ownership record.  It deliberately does *not* mean
    that the entire brokerage account is flat.

    Once this invocation starts an exit for a symbol, a later owned-position read
    never submits that symbol again.  Real fills are asynchronous, so the safe
    response is BLOCKED/pending reconciliation rather than cancel/replace churn.
    """

    def __init__(
        self,
        *,
        exit_service: LiveProtectiveExitService,
        conflict_resolver: LiveProtectiveExitConflictResolver,
        execution_flow: LiveProtectiveExitExecutionFlow,
        ownership_repository: LiveEodOwnershipRepository,
        max_passes: int = 3,
    ) -> None:
        if isinstance(max_passes, bool) or max_passes < 1:
            raise ValueError("max_passes must be a positive integer")
        self.exit_service = exit_service
        self.conflict_resolver = conflict_resolver
        self.execution_flow = execution_flow
        self.ownership_repository = ownership_repository
        self.max_passes = int(max_passes)

    def submit_all(self, *, trading_date) -> LiveEodExecutionResult:
        results: list[LiveProtectiveExitExecutionResult] = []
        submitted_symbols: set[str] = set()

        for pass_number in range(1, self.max_passes + 1):
            try:
                plans = self.exit_service.plan_end_of_day(
                    trading_date=trading_date
                ).plans
                owned_plans = self._owned_plans(plans)
            except Exception as exc:
                return LiveEodExecutionResult(
                    LiveEodExecutionDecision.BLOCKED,
                    tuple(results),
                    f"EOD ownership/position verification failed on pass "
                    f"{pass_number}: {exc}",
                )

            if not owned_plans:
                return LiveEodExecutionResult(
                    LiveEodExecutionDecision.COMPLETE,
                    tuple(results),
                    "Fresh live account verification confirms all KATANA-owned "
                    "positions are flat; unmanaged positions were not touched.",
                )

            pending = sorted(
                {candidate.code for candidate in owned_plans}
                & submitted_symbols
            )
            if pending:
                return LiveEodExecutionResult(
                    LiveEodExecutionDecision.BLOCKED,
                    tuple(results),
                    "EOD exit submission is still awaiting authoritative KATANA "
                    "position confirmation; no cancel or resubmission was attempted. "
                    f"Pending symbols: {','.join(pending)}",
                )

            for candidate in owned_plans:
                owned_quantity = self._owned_quantity(candidate.code)
                candidate_quantity = self._plan_quantity(candidate)
                if candidate_quantity != owned_quantity:
                    return self._quantity_block(
                        results=results,
                        code=candidate.code,
                        broker_quantity=candidate_quantity,
                        owned_quantity=owned_quantity,
                    )

                resolution = self.conflict_resolver.resolve_eod(
                    code=candidate.code,
                    trading_date=trading_date,
                )
                if resolution.plan is None:
                    return LiveEodExecutionResult(
                        LiveEodExecutionDecision.BLOCKED,
                        tuple(results),
                        f"EOD liquidation blocked for {candidate.code}: "
                        f"{resolution.message}",
                    )

                # resolve_eod performs another authoritative re-plan.  Validate
                # its exact SELL quantity too, preventing a manual/additional
                # holding that appeared between reads from widening our exit.
                resolved_quantity = self._plan_quantity(resolution.plan)
                if resolved_quantity != owned_quantity:
                    return self._quantity_block(
                        results=results,
                        code=candidate.code,
                        broker_quantity=resolved_quantity,
                        owned_quantity=owned_quantity,
                    )

                result = self.execution_flow._submit_plan(
                    plan=resolution.plan,
                    trading_date=trading_date,
                )
                results.append(result)
                if result.decision is LiveProtectiveExitExecutionDecision.BLOCKED:
                    return LiveEodExecutionResult(
                        LiveEodExecutionDecision.BLOCKED,
                        tuple(results),
                        f"EOD liquidation blocked for {candidate.code}.",
                    )
                if (
                    result.decision
                    is LiveProtectiveExitExecutionDecision.SUBMISSION_STARTED
                ):
                    submitted_symbols.add(candidate.code)

        try:
            remaining = self.exit_service.plan_end_of_day(
                trading_date=trading_date
            ).plans
            owned_remaining = self._owned_plans(remaining)
        except Exception as exc:
            return LiveEodExecutionResult(
                LiveEodExecutionDecision.BLOCKED,
                tuple(results),
                f"Final EOD ownership/position verification failed: {exc}",
            )

        if not owned_remaining:
            return LiveEodExecutionResult(
                LiveEodExecutionDecision.COMPLETE,
                tuple(results),
                "Final fresh live account verification confirms all KATANA-owned "
                "positions are flat; unmanaged positions were not touched.",
            )

        symbols = ",".join(sorted({plan.code for plan in owned_remaining}))
        return LiveEodExecutionResult(
            LiveEodExecutionDecision.BLOCKED,
            tuple(results),
            "EOD liquidation did not reach verified KATANA-owned flat state within "
            f"{self.max_passes} passes. Remaining symbols: {symbols}",
        )

    def _owned_plans(self, plans) -> tuple:
        ownership = self._ownership_by_code()
        result = []
        for plan in plans:
            code = str(plan.code).strip()
            record = ownership.get(code)
            if record is None:
                # Authoritative position exists, but KATANA cannot prove ownership.
                # It is deliberately invisible to liquidation.
                continue
            broker_quantity = self._plan_quantity(plan)
            if broker_quantity != int(record.quantity):
                raise RuntimeError(
                    f"KATANA ownership quantity mismatch for {code}: "
                    f"broker={broker_quantity}, owned={record.quantity}. "
                    "No EOD SELL was submitted."
                )
            result.append(plan)
        return tuple(result)

    def _ownership_by_code(self) -> dict[str, LiveProtectiveStopRecord]:
        records = tuple(self.ownership_repository.list_current())
        by_code: dict[str, LiveProtectiveStopRecord] = {}
        for record in records:
            code = str(record.code).strip()
            if not code:
                raise RuntimeError("KATANA ownership record has an empty symbol.")
            if int(record.quantity) <= 0:
                raise RuntimeError(
                    f"KATANA ownership record has invalid quantity for {code}."
                )
            if code in by_code:
                raise RuntimeError(
                    f"Multiple current KATANA ownership records exist for {code}."
                )
            by_code[code] = record
        return by_code

    def _owned_quantity(self, code: str) -> int:
        record = self._ownership_by_code().get(str(code).strip())
        if record is None:
            raise RuntimeError(
                f"KATANA ownership disappeared before EOD submission for {code}."
            )
        return int(record.quantity)

    @staticmethod
    def _plan_quantity(plan) -> int:
        order = getattr(plan, "order", None)
        quantity = getattr(order, "quantity", None)
        if isinstance(quantity, bool):
            raise RuntimeError("EOD plan contains an invalid boolean quantity.")
        try:
            normalized = int(quantity)
        except (TypeError, ValueError) as exc:
            raise RuntimeError("EOD plan does not expose a valid order quantity.") from exc
        if normalized <= 0:
            raise RuntimeError("EOD plan quantity must be positive.")
        return normalized

    @staticmethod
    def _quantity_block(
        *, results, code: str, broker_quantity: int, owned_quantity: int
    ) -> LiveEodExecutionResult:
        return LiveEodExecutionResult(
            LiveEodExecutionDecision.BLOCKED,
            tuple(results),
            f"KATANA ownership quantity mismatch for {code}: "
            f"broker={broker_quantity}, owned={owned_quantity}. "
            "No EOD SELL was submitted.",
        )
