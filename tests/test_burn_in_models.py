"""Burn-inモデルのテスト。"""

from datetime import datetime, timezone

import pytest

from app.application.trading_loop_models import (
    TradingLoopCycleStatus,
)
from app.runtime.burn_in_models import (
    BurnInCycleSample,
    BurnInResult,
    BurnInSettings,
    BurnInStopReason,
)


NOW = datetime(
    2026,
    7,
    18,
    12,
    0,
    tzinfo=timezone.utc,
)


class FakeCycle:
    def __init__(
        self,
        number: int,
        *,
        successful: bool,
    ) -> None:
        self.cycle_number = number
        self.status = (
            TradingLoopCycleStatus.COMPLETED
            if successful
            else TradingLoopCycleStatus.FAILED
        )
        self.error_message = (
            None if successful else "failed"
        )

    @property
    def is_successful(self) -> bool:
        return (
            self.status
            is TradingLoopCycleStatus.COMPLETED
        )

    @property
    def signal_count(self) -> int:
        return 0

    @property
    def execution_count(self) -> int:
        return 0


def test_settings_require_cycle_or_duration_limit() -> None:
    with pytest.raises(ValueError, match="指定"):
        BurnInSettings(
            maximum_cycles=None,
            maximum_duration_seconds=None,
        )


def test_settings_validate_values() -> None:
    with pytest.raises(ValueError, match="最大サイクル数"):
        BurnInSettings(maximum_cycles=0)

    with pytest.raises(ValueError, match="連続失敗"):
        BurnInSettings(
            maximum_consecutive_failures=0
        )


def test_result_calculates_statistics() -> None:
    result = BurnInResult(
        started_at=NOW,
        completed_at=NOW,
        stop_reason=BurnInStopReason.MAX_CYCLES_REACHED,
        samples=(
            BurnInCycleSample(
                cycle_result=FakeCycle(
                    1,
                    successful=True,
                ),
                duration_seconds=1.0,
                consecutive_failure_count=0,
            ),
            BurnInCycleSample(
                cycle_result=FakeCycle(
                    2,
                    successful=False,
                ),
                duration_seconds=3.0,
                consecutive_failure_count=1,
            ),
        ),
    )

    assert result.cycle_count == 2
    assert result.successful_cycle_count == 1
    assert result.failed_cycle_count == 1
    assert result.average_cycle_seconds == 2.0
    assert result.minimum_cycle_seconds == 1.0
    assert result.maximum_cycle_seconds == 3.0
    assert result.maximum_consecutive_failures == 1


def test_error_result_requires_message() -> None:
    with pytest.raises(
        ValueError,
        match="エラーメッセージ",
    ):
        BurnInResult(
            started_at=NOW,
            completed_at=NOW,
            stop_reason=BurnInStopReason.ERROR,
            samples=(),
        )
