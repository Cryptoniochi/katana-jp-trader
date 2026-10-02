"""Trading Cycleから保護ストップを呼ぶ統合契約テスト。"""

from datetime import datetime, timezone

from app.live.live_orchestrator import LiveTradingOrchestrator
from app.market.realtime_models import (
    MarketSessionSnapshot,
    MarketSessionState,
    RealtimeMarketPollResult,
    RealtimePollDecision,
)


class FakeMonitor:
    def poll(self, *, codes, observed_at):
        return RealtimeMarketPollResult(
            session=MarketSessionSnapshot(
                observed_at=observed_at,
                trading_date=observed_at.date(),
                is_trading_day=True,
                state=MarketSessionState.MORNING,
            ),
            decision=RealtimePollDecision.NO_NEW_BAR,
            code_count=len(tuple(codes)),
            fetched_bar_count=0,
            new_bar_count=0,
            saved_bar_count=0,
            new_bars=(),
        )


class FakePaperService:
    def process(self, prices, *, continue_on_error=False):
        raise AssertionError("5分足がないため呼ばれない")


class FakeProtectionService:
    def __init__(self):
        self.call_count = 0

    def process_pending(self):
        self.call_count += 1


def test_protection_runs_even_when_no_completed_bar_exists():
    protection = FakeProtectionService()
    orchestrator = LiveTradingOrchestrator(
        market_monitor=FakeMonitor(),
        paper_trading_service=FakePaperService(),
        cycle_protection_service=protection,
        now_provider=lambda: datetime(
            2026, 10, 5, 0, 30, tzinfo=timezone.utc
        ),
    )

    result = orchestrator.run_cycle(
        cycle_number=1,
        codes=("7203",),
    )

    assert result.is_completed
    assert protection.call_count == 1
