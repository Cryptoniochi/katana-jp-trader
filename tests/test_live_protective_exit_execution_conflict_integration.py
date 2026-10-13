from dataclasses import dataclass
from datetime import date, datetime, timezone

import pytest

from app.live.live_protective_exit_conflict_resolver import (
    LiveConflictResolutionDecision,
    LiveConflictResolutionResult,
)
from app.live.live_protective_exit_execution_flow import (
    LiveProtectiveExitExecutionDecision,
    LiveProtectiveExitExecutionFlow,
)
from app.live.live_protective_exit_service import (
    LiveProtectiveExitDecision,
    LiveProtectiveExitService,
)

DAY = date(2026, 10, 13)
NOW = datetime(2026, 10, 13, 6, 30, tzinfo=timezone.utc)


@dataclass(frozen=True)
class Position:
    code: str
    quantity: int


@dataclass(frozen=True)
class State:
    positions: tuple[Position, ...]


class Account:
    def __init__(self, quantity=100):
        self.quantity = quantity

    def refresh(self):
        positions = () if self.quantity == 0 else (Position("3911", self.quantity),)
        return State(positions)


class Tracking:
    def __init__(self):
        self.calls = []

    def submit(self, **kwargs):
        self.calls.append(kwargs)
        return object()


class Resolver:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def resolve_stop_loss(self, **kwargs):
        self.calls.append(kwargs)
        return self.result


def exit_service(account):
    return LiveProtectiveExitService(
        account_state_provider=account,
        market_price_provider=lambda _code: 190,
        now_provider=lambda: NOW,
    )


def required_plan(quantity=40):
    service = exit_service(Account(quantity))
    return service.evaluate_stop_loss(
        code="3911", stop_price=200, trading_date=DAY
    )


def test_conflict_resolver_is_mandatory():
    with pytest.raises(TypeError):
        LiveProtectiveExitExecutionFlow(
            exit_service=exit_service(Account()),
            tracking_flow=Tracking(),
        )


def test_replanned_quantity_is_the_quantity_sent_to_tracking():
    plan = required_plan(40)
    resolver = Resolver(
        LiveConflictResolutionResult(
            LiveConflictResolutionDecision.REPLANNED,
            plan,
            "replanned",
        )
    )
    tracking = Tracking()
    flow = LiveProtectiveExitExecutionFlow(
        exit_service=exit_service(Account(100)),
        tracking_flow=tracking,
        conflict_resolver=resolver,
    )
    result = flow.submit_stop_loss(
        code="3911", stop_price=200, trading_date=DAY
    )
    assert result.decision is LiveProtectiveExitExecutionDecision.SUBMISSION_STARTED
    assert len(tracking.calls) == 1
    assert tracking.calls[0]["order"].quantity == 40
    assert tracking.calls[0]["required_baseline_quantity"] == 40


def test_blocked_resolution_never_reaches_tracking():
    resolver = Resolver(
        LiveConflictResolutionResult(
            LiveConflictResolutionDecision.BLOCKED,
            None,
            "ambiguous cancel",
        )
    )
    tracking = Tracking()
    flow = LiveProtectiveExitExecutionFlow(
        exit_service=exit_service(Account(100)),
        tracking_flow=tracking,
        conflict_resolver=resolver,
    )
    result = flow.submit_stop_loss(
        code="3911", stop_price=200, trading_date=DAY
    )
    assert result.decision is LiveProtectiveExitExecutionDecision.BLOCKED
    assert tracking.calls == []


def test_zero_position_after_resolution_never_reaches_tracking():
    service = exit_service(Account(0))
    plan = service.evaluate_stop_loss(
        code="3911", stop_price=200, trading_date=DAY
    )
    assert plan.decision is LiveProtectiveExitDecision.NO_POSITION
    resolver = Resolver(
        LiveConflictResolutionResult(
            LiveConflictResolutionDecision.REPLANNED,
            plan,
            "flat",
        )
    )
    tracking = Tracking()
    flow = LiveProtectiveExitExecutionFlow(
        exit_service=service,
        tracking_flow=tracking,
        conflict_resolver=resolver,
    )
    result = flow.submit_stop_loss(
        code="3911", stop_price=200, trading_date=DAY
    )
    assert result.decision is LiveProtectiveExitExecutionDecision.NO_ACTION
    assert tracking.calls == []
