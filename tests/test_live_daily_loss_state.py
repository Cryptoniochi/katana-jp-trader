"""Live日次損失状態Providerのテスト。"""

from datetime import datetime, timezone

import pytest

from app.live.live_daily_loss_state import (
    LiveDailyLossStateProvider,
)
from app.runtime.daily_report_service import DailyTradeRecord


NOW = datetime(2026, 10, 3, 1, 0, tzinfo=timezone.utc)


def _record(
    pnl: float,
    minute: int,
) -> DailyTradeRecord:
    return DailyTradeRecord(
        closed_at=datetime(
            2026, 10, 3, 0, minute, tzinfo=timezone.utc
        ),
        symbol="7203",
        strategy_name="test",
        realized_profit_loss=pnl,
    )


class StubRepository:
    def __init__(self, records=()):
        self.records = tuple(records)
        self.requested_dates = []

    def list_closed_trades(self, report_date):
        self.requested_dates.append(report_date)
        return self.records


def _provider(records=(), now=NOW):
    repository = StubRepository(records)
    provider = LiveDailyLossStateProvider(
        repository=repository,
        now_provider=lambda: now,
    )
    return provider, repository


def test_empty_day_has_zero_realized_profit_loss():
    provider, _ = _provider()
    assert provider.daily_realized_profit_loss() == 0.0


def test_empty_day_has_zero_consecutive_losses():
    provider, _ = _provider()
    assert provider.consecutive_loss_count() == 0


def test_daily_profit_loss_sums_closed_trades():
    provider, _ = _provider(
        [_record(1000.0, 1), _record(-400.0, 2)]
    )
    assert provider.daily_realized_profit_loss() == 600.0


def test_trailing_losses_are_counted():
    provider, _ = _provider(
        [
            _record(1000.0, 1),
            _record(-100.0, 2),
            _record(-200.0, 3),
        ]
    )
    assert provider.consecutive_loss_count() == 2


def test_profit_breaks_consecutive_loss_sequence():
    provider, _ = _provider(
        [
            _record(-100.0, 1),
            _record(200.0, 2),
            _record(-300.0, 3),
        ]
    )
    assert provider.consecutive_loss_count() == 1


def test_flat_trade_breaks_consecutive_loss_sequence():
    provider, _ = _provider(
        [
            _record(-100.0, 1),
            _record(0.0, 2),
            _record(-300.0, 3),
        ]
    )
    assert provider.consecutive_loss_count() == 1


def test_all_losses_are_counted():
    provider, _ = _provider(
        [
            _record(-100.0, 1),
            _record(-200.0, 2),
            _record(-300.0, 3),
        ]
    )
    assert provider.consecutive_loss_count() == 3


def test_repository_receives_tokyo_trading_date():
    provider, repository = _provider(
        now=datetime(
            2026, 10, 2, 16, 0, tzinfo=timezone.utc
        )
    )
    provider.daily_realized_profit_loss()
    assert str(repository.requested_dates[-1]) == "2026-10-03"


def test_repository_error_is_not_hidden():
    class FailingRepository:
        def list_closed_trades(self, report_date):
            raise RuntimeError("database unavailable")

    provider = LiveDailyLossStateProvider(
        repository=FailingRepository(),
        now_provider=lambda: NOW,
    )

    with pytest.raises(RuntimeError, match="database unavailable"):
        provider.consecutive_loss_count()


def test_non_finite_profit_loss_is_rejected():
    provider, _ = _provider([_record(float("nan"), 1)])

    with pytest.raises(ValueError, match="有限値"):
        provider.daily_realized_profit_loss()


def test_out_of_order_records_are_rejected():
    provider, _ = _provider(
        [_record(-100.0, 2), _record(-200.0, 1)]
    )

    with pytest.raises(ValueError, match="closed_at昇順"):
        provider.consecutive_loss_count()


def test_naive_now_is_rejected():
    provider, _ = _provider(
        now=datetime(2026, 10, 3, 1, 0)
    )

    with pytest.raises(ValueError, match="タイムゾーン"):
        provider.daily_realized_profit_loss()
