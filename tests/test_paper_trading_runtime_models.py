"""Paper Trading Runtimeモデルのテスト。"""

from datetime import datetime, timezone

import pytest

from app.application.trading_loop_models import (
    TradingLoopCycleStatus,
)
from app.runtime.paper_trading_runtime_models import (
    PaperTradingCycleRecord,
    PaperTradingDailySummary,
    PaperTradingRuntimeStatus,
)


NOW = datetime(
    2026,
    7,
    18,
    0,
    0,
    tzinfo=timezone.utc,
)


class FakeCycle:
    def __init__(
        self,
        number: int,
        status: TradingLoopCycleStatus,
    ) -> None:
        self.cycle_number = number
        self.status = status
        self.error_message = (
            None
            if status is TradingLoopCycleStatus.COMPLETED
            else "failed"
        )

    @property
    def is_successful(self) -> bool:
        return (
            self.status
            is TradingLoopCycleStatus.COMPLETED
        )

    @property
    def signal_count(self) -> int:
        return 2

    @property
    def execution_count(self) -> int:
        return 1


def record(
    number: int,
    status: TradingLoopCycleStatus,
) -> PaperTradingCycleRecord:
    return PaperTradingCycleRecord(
        cycle_result=FakeCycle(number, status),
        portfolio_snapshot=None,
    )


def test_daily_summary_calculates_counts_and_return() -> None:
    summary = PaperTradingDailySummary(
        trading_date=NOW.date(),
        started_at=NOW,
        completed_at=NOW,
        status=PaperTradingRuntimeStatus.COMPLETED,
        records=(
            record(
                1,
                TradingLoopCycleStatus.COMPLETED,
            ),
            record(
                2,
                TradingLoopCycleStatus.FAILED,
            ),
        ),
        initial_equity=1_000_000.0,
        final_equity=1_010_000.0,
    )

    assert summary.cycle_count == 2
    assert summary.successful_cycle_count == 1
    assert summary.failed_cycle_count == 1
    assert summary.signal_count == 4
    assert summary.execution_count == 2
    assert summary.net_profit_loss == 10_000.0
    assert summary.return_rate == pytest.approx(0.01)


def test_failed_summary_requires_error_message() -> None:
    with pytest.raises(
        ValueError,
        match="エラーメッセージ",
    ):
        PaperTradingDailySummary(
            trading_date=NOW.date(),
            started_at=NOW,
            completed_at=NOW,
            status=PaperTradingRuntimeStatus.FAILED,
            records=(),
            initial_equity=1_000_000.0,
            final_equity=1_000_000.0,
        )


def test_summary_requires_consecutive_cycles() -> None:
    with pytest.raises(ValueError, match="連番"):
        PaperTradingDailySummary(
            trading_date=NOW.date(),
            started_at=NOW,
            completed_at=NOW,
            status=PaperTradingRuntimeStatus.COMPLETED,
            records=(
                record(
                    2,
                    TradingLoopCycleStatus.COMPLETED,
                ),
            ),
            initial_equity=1_000_000.0,
            final_equity=1_000_000.0,
        )
