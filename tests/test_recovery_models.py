"""Recovery共通モデルのテスト。"""

from datetime import datetime, timezone

import pytest

from app.runtime.recovery_models import (
    RecoveryAttempt,
    RecoveryPolicy,
    RecoveryResult,
    RecoveryStatus,
)


NOW = datetime(
    2026,
    7,
    18,
    0,
    0,
    tzinfo=timezone.utc,
)


def test_policy_calculates_capped_backoff() -> None:
    policy = RecoveryPolicy(
        maximum_attempts=5,
        initial_delay_seconds=2.0,
        backoff_multiplier=3.0,
        maximum_delay_seconds=10.0,
    )

    assert policy.delay_seconds_for_attempt(1) == 2.0
    assert policy.delay_seconds_for_attempt(2) == 6.0
    assert policy.delay_seconds_for_attempt(3) == 10.0


def test_policy_rejects_invalid_values() -> None:
    with pytest.raises(
        ValueError,
        match="最大試行回数",
    ):
        RecoveryPolicy(maximum_attempts=0)


def test_success_result_requires_successful_final_attempt() -> None:
    failed_attempt = RecoveryAttempt(
        attempt_number=1,
        started_at=NOW,
        completed_at=NOW,
        successful=False,
        error_message="failed",
        delay_seconds_before_attempt=0.0,
    )

    with pytest.raises(
        ValueError,
        match="SUCCESS",
    ):
        RecoveryResult(
            recovery_name="broker reconnect",
            status=RecoveryStatus.SUCCESS,
            started_at=NOW,
            completed_at=NOW,
            attempts=(failed_attempt,),
        )
