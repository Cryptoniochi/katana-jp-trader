"""Phase 6-C Step 4B-1 tests for runtime safety-state freshness."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pytest

from app.live.live_runtime_safety_state import LiveRuntimeSafetyStateProvider
from app.supervisor.fault_tolerance_models import FaultToleranceDecision


NOW = datetime(2026, 10, 3, 4, 0, 0, tzinfo=timezone.utc)


@dataclass(frozen=True)
class _Report:
    generated_at: datetime
    state: str = "consistent"
    consistent: bool = True
    live_order_ready: bool = False


@dataclass(frozen=True)
class _Attempt:
    checked_at: datetime
    decision: FaultToleranceDecision


def _provider(
    *,
    report=None,
    attempt=None,
    report_provider=None,
    attempt_provider=None,
    maximum_age=timedelta(minutes=2),
    future_skew=timedelta(seconds=5),
):
    return LiveRuntimeSafetyStateProvider(
        reconciliation_report_provider=(
            report_provider
            if report_provider is not None
            else lambda: report
        ),
        fault_tolerance_attempt_provider=(
            attempt_provider
            if attempt_provider is not None
            else lambda: attempt
        ),
        maximum_reconciliation_age=maximum_age,
        maximum_future_skew=future_skew,
        now_provider=lambda: NOW,
    )


def test_fresh_consistent_report_without_fault_attempt_is_safe():
    provider = _provider(
        report=_Report(generated_at=NOW - timedelta(seconds=30)),
    )

    snapshot = provider()

    assert snapshot.safe_stop_active is False
    assert snapshot.reconciliation_consistent is True
    assert snapshot.reconciliation_state == "consistent"


def test_safe_stop_attempt_always_blocks():
    provider = _provider(
        report=_Report(generated_at=NOW),
        attempt=_Attempt(
            checked_at=NOW,
            decision=FaultToleranceDecision.SAFE_STOP,
        ),
    )

    snapshot = provider()

    assert snapshot.safe_stop_active is True
    assert snapshot.is_blocked


def test_stale_reconciliation_fails_closed():
    provider = _provider(
        report=_Report(generated_at=NOW - timedelta(minutes=3)),
    )

    snapshot = provider()

    assert snapshot.is_blocked
    assert snapshot.reconciliation_state == "reconciliation_stale"


def test_report_too_far_in_future_fails_closed():
    provider = _provider(
        report=_Report(generated_at=NOW + timedelta(seconds=6)),
    )

    snapshot = provider()

    assert snapshot.is_blocked
    assert snapshot.reconciliation_state == "reconciliation_from_future"


def test_missing_reconciliation_fails_closed():
    snapshot = _provider(report=None)()

    assert snapshot.is_blocked
    assert snapshot.reconciliation_state == "reconciliation_missing"


def test_reconciliation_provider_failure_fails_closed():
    def fail():
        raise RuntimeError("read failed")

    snapshot = _provider(report_provider=fail)()

    assert snapshot.is_blocked
    assert snapshot.reconciliation_state == "reconciliation_unavailable"


def test_fault_tolerance_provider_failure_fails_closed():
    def fail():
        raise RuntimeError("fault state failed")

    snapshot = _provider(
        report=_Report(generated_at=NOW),
        attempt_provider=fail,
    )()

    assert snapshot.is_blocked
    assert snapshot.reconciliation_state == "fault_tolerance_unavailable"


def test_inconsistent_fresh_report_remains_blocked():
    provider = _provider(
        report=_Report(
            generated_at=NOW,
            state="blocked",
            consistent=False,
        ),
    )

    snapshot = provider()

    assert snapshot.is_blocked
    assert snapshot.safe_stop_active is False
    assert snapshot.reconciliation_consistent is False
    assert snapshot.reconciliation_state == "blocked"


def test_exact_age_boundary_is_accepted():
    provider = _provider(
        report=_Report(generated_at=NOW - timedelta(minutes=2)),
    )

    assert provider().is_blocked is False


def test_exact_future_skew_boundary_is_accepted():
    provider = _provider(
        report=_Report(generated_at=NOW + timedelta(seconds=5)),
    )

    assert provider().is_blocked is False


def test_invalid_age_configuration_is_rejected():
    with pytest.raises(ValueError):
        _provider(maximum_age=timedelta(0))


def test_invalid_future_skew_configuration_is_rejected():
    with pytest.raises(ValueError):
        _provider(future_skew=timedelta(seconds=-1))


def test_naive_now_provider_is_rejected():
    provider = LiveRuntimeSafetyStateProvider(
        reconciliation_report_provider=lambda: _Report(generated_at=NOW),
        fault_tolerance_attempt_provider=lambda: None,
        now_provider=lambda: datetime(2026, 10, 3, 4, 0, 0),
    )

    with pytest.raises(ValueError):
        provider()


def test_naive_report_timestamp_fails_closed():
    provider = _provider(
        report=_Report(
            generated_at=datetime(2026, 10, 3, 4, 0, 0),
        ),
    )

    snapshot = provider()

    assert snapshot.is_blocked
    assert snapshot.reconciliation_state == "reconciliation_timestamp_invalid"
