"""日次損失ProviderとKill Switch Providerの接続テスト。"""

from datetime import datetime, timezone

from app.live.live_daily_loss_state import (
    LiveDailyLossStateProvider,
)
from app.live.live_runtime_kill_switch_state import (
    LiveRuntimeKillSwitchStateProvider,
)
from app.risk.kill_switch_service import KillSwitchService
from app.runtime.daily_report_service import DailyTradeRecord


NOW = datetime(2026, 10, 3, 1, 0, tzinfo=timezone.utc)


class StubRepository:
    def __init__(self, records):
        self.records = tuple(records)

    def list_closed_trades(self, report_date):
        return self.records


def _record(pnl, minute):
    return DailyTradeRecord(
        closed_at=datetime(
            2026, 10, 3, 0, minute, tzinfo=timezone.utc
        ),
        symbol="7203",
        strategy_name="test",
        realized_profit_loss=pnl,
    )


def _kill_provider(records):
    loss_state = LiveDailyLossStateProvider(
        repository=StubRepository(records),
        now_provider=lambda: NOW,
    )
    return LiveRuntimeKillSwitchStateProvider(
        manual_blocked_provider=lambda: False,
        daily_profit_loss_provider=(
            loss_state.daily_realized_profit_loss
        ),
        consecutive_loss_count_provider=(
            loss_state.consecutive_loss_count
        ),
        runtime_health_ok_provider=lambda: True,
        heartbeat_alive_provider=lambda: True,
        broker_available_provider=lambda: True,
        now_provider=lambda: NOW,
    )


def test_real_trade_sequence_blocks_at_three_losses():
    provider = _kill_provider(
        [
            _record(-100.0, 1),
            _record(-200.0, 2),
            _record(-300.0, 3),
        ]
    )

    evaluation = KillSwitchService().evaluate(provider())

    assert evaluation.is_blocked is True
    assert evaluation.metadata["consecutive_loss_blocked"] is True


def test_real_trade_sum_blocks_at_daily_loss_limit():
    provider = _kill_provider(
        [
            _record(-25_000.0, 1),
            _record(-25_000.0, 2),
        ]
    )

    evaluation = KillSwitchService().evaluate(provider())

    assert evaluation.is_blocked is True
    assert evaluation.metadata["daily_loss_blocked"] is True


def test_real_trade_state_allows_when_below_limits():
    provider = _kill_provider(
        [
            _record(5_000.0, 1),
            _record(-1_000.0, 2),
        ]
    )

    evaluation = KillSwitchService().evaluate(provider())

    assert evaluation.allows_new_entries is True
