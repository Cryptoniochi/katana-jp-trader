"""RuntimeRecoveryResultモデルのテスト。"""

from datetime import datetime, timezone

import pytest

from app.runtime.runtime_health_monitor_models import (
    RuntimeHealthMonitorReport,
    RuntimeHealthStatus,
)
from app.runtime.runtime_recovery_models import (
    RuntimeRecoveryResult,
)


NOW = datetime(
    2026,
    7,
    18,
    0,
    0,
    tzinfo=timezone.utc,
)


def health(
    status: RuntimeHealthStatus,
) -> RuntimeHealthMonitorReport:
    reasons = (
        ()
        if status in {
            RuntimeHealthStatus.HEALTHY,
            RuntimeHealthStatus.IDLE,
        }
        else ("runtime issue",)
    )

    return RuntimeHealthMonitorReport(
        status=status,
        checked_at=NOW,
        running=(
            status
            is not RuntimeHealthStatus.STOPPED
        ),
        heartbeat_age_seconds=10.0,
        cycle_age_seconds=20.0,
        reasons=reasons,
    )


def test_healthy_result_requires_no_recovery() -> None:
    initial = health(
        RuntimeHealthStatus.HEALTHY
    )

    result = RuntimeRecoveryResult(
        runtime_name="paper-runtime",
        initial_health=initial,
        recovery_result=None,
        final_health=initial,
    )

    assert result.recovery_attempted is False
    assert result.recovered is True
    assert result.requires_attention is False


def test_result_rejects_recovery_for_healthy_runtime() -> None:
    from app.runtime.recovery_models import (
        RecoveryAttempt,
        RecoveryResult,
        RecoveryStatus,
    )

    attempt = RecoveryAttempt(
        attempt_number=1,
        started_at=NOW,
        completed_at=NOW,
        successful=True,
        error_message=None,
        delay_seconds_before_attempt=0.0,
    )
    recovery = RecoveryResult(
        recovery_name="paper-runtime restart",
        status=RecoveryStatus.SUCCESS,
        started_at=NOW,
        completed_at=NOW,
        attempts=(attempt,),
    )

    with pytest.raises(
        ValueError,
        match="正常Runtime",
    ):
        RuntimeRecoveryResult(
            runtime_name="paper-runtime",
            initial_health=health(
                RuntimeHealthStatus.HEALTHY
            ),
            recovery_result=recovery,
            final_health=health(
                RuntimeHealthStatus.HEALTHY
            ),
        )
