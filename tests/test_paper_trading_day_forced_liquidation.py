"""Sprint 117: 停止要求時も市場終了後の全決済を保証する。"""

from datetime import date, datetime, timezone
from types import SimpleNamespace

from app.market.market_session import TokyoMarketSession
from app.runtime.paper_trading_day_models import (
    PaperTradingDayStopReason,
)
from app.runtime.paper_trading_day_service import (
    PaperTradingDayService,
)


NOW = datetime(2026, 8, 5, 6, 35, tzinfo=timezone.utc)


class FakeRuntime:
    def __init__(self) -> None:
        self.completed = False
        self.failed = False

    def start(self) -> None:
        pass

    def run_cycle(self):
        raise AssertionError("cycle must not run")

    def complete(self):
        self.completed = True
        return SimpleNamespace(trading_date=date(2026, 8, 5))

    def fail(self, *, error_message: str):
        self.failed = True
        return SimpleNamespace(trading_date=date(2026, 8, 5))


class FakePersister:
    def persist(self, _summary):
        return SimpleNamespace(
            record=SimpleNamespace(
                trading_date=date(2026, 8, 5)
            )
        )


class AfterCloseClock:
    def snapshot(self, _now):
        return SimpleNamespace(
            session=TokyoMarketSession.AFTER_CLOSE,
            is_open=False,
            wait_seconds=0.0,
        )


class FakeLiquidator:
    def __init__(self) -> None:
        self.calls = 0

    def close_all_positions(self):
        self.calls += 1
        return SimpleNamespace(
            completed=True,
            remaining_position_count=0,
        )


def test_stop_request_after_close_liquidates_before_complete() -> None:
    runtime = FakeRuntime()
    liquidator = FakeLiquidator()
    service = PaperTradingDayService(
        runtime=runtime,
        persistence_service=FakePersister(),
        market_clock=AfterCloseClock(),
        end_of_day_liquidator=liquidator,
        now_provider=lambda: NOW,
        stop_requested=lambda: True,
    )

    result = service.run()

    assert result.stop_reason is PaperTradingDayStopReason.STOP_REQUESTED
    assert liquidator.calls == 1
    assert runtime.completed is True
    assert runtime.failed is False


def test_missing_liquidator_preserves_legacy_behavior() -> None:
    runtime = FakeRuntime()
    service = PaperTradingDayService(
        runtime=runtime,
        persistence_service=FakePersister(),
        market_clock=AfterCloseClock(),
        end_of_day_liquidator=None,
        now_provider=lambda: NOW,
        stop_requested=lambda: True,
    )

    result = service.run()

    assert result.stop_reason is PaperTradingDayStopReason.STOP_REQUESTED
    assert runtime.completed is True
    assert runtime.failed is False
