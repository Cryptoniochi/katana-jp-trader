"""Paper Trading Dayモデルのテスト。"""

from datetime import datetime, timezone

import pytest

from app.runtime.paper_trading_daily_repository import (
    PaperTradingDailyRecord,
)
from app.runtime.paper_trading_day_models import (
    PaperTradingDayResult,
    PaperTradingDayStopReason,
    PaperTradingDaySettings,
)
from app.runtime.paper_trading_runtime_models import (
    PaperTradingDailySummary,
    PaperTradingRuntimeStatus,
)


NOW = datetime(
    2026,
    7,
    21,
    0,
    0,
    tzinfo=timezone.utc,
)


def summary() -> PaperTradingDailySummary:
    return PaperTradingDailySummary(
        trading_date=NOW.date(),
        started_at=NOW,
        completed_at=NOW,
        status=PaperTradingRuntimeStatus.COMPLETED,
        records=(),
        initial_equity=1_000_000.0,
        final_equity=1_010_000.0,
    )


def record() -> PaperTradingDailyRecord:
    return PaperTradingDailyRecord(
        trading_date=NOW.date(),
        status=PaperTradingRuntimeStatus.COMPLETED,
        started_at=NOW,
        completed_at=NOW,
        cycle_count=0,
        successful_cycle_count=0,
        failed_cycle_count=0,
        signal_count=0,
        execution_count=0,
        initial_equity=1_000_000.0,
        final_equity=1_010_000.0,
        net_profit_loss=10_000.0,
        return_rate=0.01,
        error_message=None,
        payload={},
        created_at=NOW,
        updated_at=NOW,
    )


def test_settings_validate_values() -> None:
    with pytest.raises(ValueError, match="0秒以上"):
        PaperTradingDaySettings(
            cycle_interval_seconds=-1.0
        )

    with pytest.raises(ValueError, match="0より大きい"):
        PaperTradingDaySettings(
            maximum_cycles=0
        )


def test_result_exposes_daily_values() -> None:
    result = PaperTradingDayResult(
        trading_date=NOW.date(),
        started_at=NOW,
        completed_at=NOW,
        stop_reason=PaperTradingDayStopReason.MARKET_CLOSED,
        summary=summary(),
        record=record(),
    )

    assert result.cycle_count == 0
    assert result.net_profit_loss == 10_000.0
    assert result.return_rate == pytest.approx(0.01)


def test_error_result_requires_message() -> None:
    with pytest.raises(
        ValueError,
        match="エラーメッセージ",
    ):
        PaperTradingDayResult(
            trading_date=NOW.date(),
            started_at=NOW,
            completed_at=NOW,
            stop_reason=PaperTradingDayStopReason.ERROR,
            summary=summary(),
            record=record(),
        )
