"""Trading Loop Runnerモデルのテスト。"""

from datetime import datetime, timezone

import pytest

from app.application.trading_loop_runner_models import (
    TradingLoopRunnerResult,
    TradingLoopRunnerSettings,
    TradingLoopRunnerStopReason,
)


NOW = datetime(
    2026,
    7,
    18,
    12,
    0,
    tzinfo=timezone.utc,
)


def test_settings_validate_interval_and_cycle_limit() -> None:
    with pytest.raises(ValueError, match="0秒以上"):
        TradingLoopRunnerSettings(
            cycle_interval_seconds=-1.0
        )

    with pytest.raises(ValueError, match="0より大きい"):
        TradingLoopRunnerSettings(
            maximum_cycles=0
        )


def test_empty_result_is_valid_for_stop_request() -> None:
    result = TradingLoopRunnerResult(
        started_at=NOW,
        completed_at=NOW,
        stop_reason=(
            TradingLoopRunnerStopReason.STOP_REQUESTED
        ),
        cycles=(),
    )

    assert result.cycle_count == 0
    assert result.successful_cycle_count == 0
    assert result.failed_cycle_count == 0


def test_error_result_requires_message() -> None:
    with pytest.raises(
        ValueError,
        match="エラーメッセージ",
    ):
        TradingLoopRunnerResult(
            started_at=NOW,
            completed_at=NOW,
            stop_reason=(
                TradingLoopRunnerStopReason.ERROR
            ),
            cycles=(),
        )
