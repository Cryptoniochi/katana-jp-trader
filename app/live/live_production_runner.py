"""Live-only production cycle boundary for Project KATANA.

This module deliberately contains no PaperBroker dependency and performs no
broker action by itself. It is the application boundary driven by the
production market-session loop.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Callable, Protocol, Sequence

from app.live.execution_mode import (
    ExecutionModeSettings,
    LiveArmingPolicy,
    TradingExecutionMode,
)


class LiveProductionRunnerError(RuntimeError):
    """Raised when the Live production boundary cannot safely run."""


class LiveCycleDecision(StrEnum):
    NO_ACTION = "no_action"
    SUBMISSION_STARTED = "submission_started"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class LiveEntryIntent:
    """Broker-independent entry intent produced by the strategy layer."""

    execution_key: str
    code: str
    quantity: int
    side: str = "BUY"

    def __post_init__(self) -> None:
        if not self.execution_key.strip():
            raise ValueError("execution_key must not be blank.")
        if not self.code.strip():
            raise ValueError("code must not be blank.")
        if isinstance(self.quantity, bool) or self.quantity <= 0:
            raise ValueError("quantity must be greater than zero.")
        if self.side.upper() != "BUY":
            raise ValueError("Live entry intent currently permits BUY only.")


class LiveEntrySubmitter(Protocol):
    def __call__(self, intent: LiveEntryIntent, trading_date: date) -> object:
        """Submit one already-normalized entry through the final Live flow."""


class LiveProtectiveCycle(Protocol):
    def __call__(self, trading_date: date) -> object:
        """Evaluate/reconcile Live protection state."""


@dataclass(frozen=True, slots=True)
class LiveProductionCycleResult:
    decision: LiveCycleDecision
    attempted_entries: int = 0
    started_entries: int = 0
    message: str = ""


class LiveProductionRunner:
    """Fail-closed Live application runner with no Paper/Shadow fallback."""

    def __init__(
        self,
        *,
        execution_settings: ExecutionModeSettings,
        entry_intent_provider: Callable[[], Sequence[LiveEntryIntent]],
        entry_submitter: LiveEntrySubmitter,
        protective_cycle: LiveProtectiveCycle,
        reconciliation_cycle: LiveProtectiveCycle | None = None,
        position_protection_reconciliation: LiveProtectiveCycle | None = None,
        strategy_exit_cycle: LiveProtectiveCycle | None = None,
        arming_policy: LiveArmingPolicy | None = None,
    ) -> None:
        self.execution_settings = execution_settings
        self.entry_intent_provider = entry_intent_provider
        self.entry_submitter = entry_submitter
        self.protective_cycle = protective_cycle
        self.reconciliation_cycle = reconciliation_cycle
        self.position_protection_reconciliation = position_protection_reconciliation
        self.strategy_exit_cycle = strategy_exit_cycle
        self.arming_policy = arming_policy or LiveArmingPolicy()

    def run_cycle(self, *, trading_date: date) -> LiveProductionCycleResult:
        """Run one authorized Live cycle.

        Prior submissions and protective state are reconciled first. The realtime
        signal engine is then evaluated exactly once by entry_intent_provider.
        Strategy exits from that same evaluation are processed before any new BUY.
        Any unresolved exit blocks new risk for the cycle.
        """
        if self.execution_settings.mode is not TradingExecutionMode.LIVE:
            raise LiveProductionRunnerError(
                "LiveProductionRunner requires KATANA execution mode LIVE."
            )
        self.arming_policy.require_authorized(
            self.execution_settings,
            trading_date=trading_date,
        )

        if self.reconciliation_cycle is not None:
            reconciliation = self.reconciliation_cycle(trading_date)
            if int(getattr(reconciliation, "blocked", 0) or 0) > 0:
                return LiveProductionCycleResult(
                    decision=LiveCycleDecision.BLOCKED,
                    message="Live entry reconciliation is unresolved; new entries blocked.",
                )

        if self.position_protection_reconciliation is not None:
            position_protection = self.position_protection_reconciliation(trading_date)
            if int(getattr(position_protection, "blocked", 0) or 0) > 0:
                return LiveProductionCycleResult(
                    decision=LiveCycleDecision.BLOCKED,
                    message=(
                        "Live position/protective-stop reconciliation is unresolved; "
                        "new entries blocked."
                    ),
                )

        protection = self.protective_cycle(trading_date)
        if int(getattr(protection, "blocked", 0) or 0) > 0:
            return LiveProductionCycleResult(
                decision=LiveCycleDecision.BLOCKED,
                message="Live protective-stop state is unresolved; new entries blocked.",
            )

        # This call evaluates RealtimeSignalEngine exactly once.
        intents = tuple(self.entry_intent_provider())

        # SELL/EXIT signals from the same engine evaluation are handled before BUY.
        if self.strategy_exit_cycle is not None:
            exits = self.strategy_exit_cycle(trading_date)
            if int(getattr(exits, "blocked", 0) or 0) > 0:
                return LiveProductionCycleResult(
                    decision=LiveCycleDecision.BLOCKED,
                    attempted_entries=len(intents),
                    message="Live strategy exit is unresolved; new entries blocked.",
                )
            if int(getattr(exits, "submitted", 0) or 0) > 0:
                # Do not open fresh risk in the same cycle that started a SELL.
                return LiveProductionCycleResult(
                    decision=LiveCycleDecision.SUBMISSION_STARTED,
                    attempted_entries=len(intents),
                    message="Live strategy exit submission started; new entries deferred.",
                )

        if not intents:
            return LiveProductionCycleResult(
                decision=LiveCycleDecision.NO_ACTION,
                message="No Live entry intents were produced.",
            )

        started = 0
        for intent in intents:
            result = self.entry_submitter(intent, trading_date)
            if result is not None and result is not False:
                started += 1

        return LiveProductionCycleResult(
            decision=(
                LiveCycleDecision.SUBMISSION_STARTED
                if started
                else LiveCycleDecision.BLOCKED
            ),
            attempted_entries=len(intents),
            started_entries=started,
            message=(
                "Live entry submission started."
                if started
                else "All Live entry intents were blocked."
            ),
        )
