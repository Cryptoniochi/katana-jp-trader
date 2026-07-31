"""Paper Trading事前リスク判定のテスト。"""

from datetime import datetime, timezone
from types import SimpleNamespace

from app.risk.paper_trading_pretrade_risk import (
    PaperTradingPreTradeRiskProvider,
    PaperTradingRiskLimits,
)
from app.trading.signal_models import SignalAction, TradeSignal


class FakeBroker:
    def __init__(
        self,
        *,
        equity=10_000_000.0,
        cash=10_000_000.0,
        positions=(),
    ):
        self.account = SimpleNamespace(
            equity=equity,
            cash_balance=cash,
        )
        self.positions = list(positions)

    def get_account(self):
        return self.account

    def list_positions(self):
        return list(self.positions)


def signal(
    *,
    action=SignalAction.BUY,
    code="7203",
    price=2500.0,
    quantity=100,
):
    return TradeSignal(
        signal_id=f"signal-{code}-{action.value}",
        code=code,
        strategy_name="test",
        action=action,
        generated_at=datetime.now(timezone.utc),
        signal_price=price,
        quantity=quantity,
        reason="test",
    )


def test_blocks_order_value_over_limit() -> None:
    provider = PaperTradingPreTradeRiskProvider(
        broker=FakeBroker(),
        limits=PaperTradingRiskLimits(
            max_position_value=100_000.0,
        ),
    )
    provider.prepare(signal(), 2500.0)

    result = provider()

    assert result.is_blocked
    assert result.reason == "max_position_value_exceeded"


def test_blocks_when_daily_loss_reached() -> None:
    broker = FakeBroker()
    provider = PaperTradingPreTradeRiskProvider(
        broker=broker,
        limits=PaperTradingRiskLimits(
            max_daily_loss=100_000.0,
        ),
    )
    broker.account = SimpleNamespace(
        equity=9_899_999.0,
        cash_balance=9_899_999.0,
    )
    provider.prepare(signal(), 2500.0)

    result = provider()

    assert result.is_blocked
    assert result.reason == "max_daily_loss_reached"


def test_exit_is_allowed_after_daily_loss() -> None:
    broker = FakeBroker()
    provider = PaperTradingPreTradeRiskProvider(
        broker=broker,
        limits=PaperTradingRiskLimits(
            max_daily_loss=100_000.0,
        ),
    )
    broker.account = SimpleNamespace(
        equity=9_800_000.0,
        cash_balance=9_800_000.0,
    )
    provider.prepare(
        signal(action=SignalAction.EXIT),
        2500.0,
    )

    result = provider()

    assert result.allows_new_entries
    assert result.reason == "exit_order_allowed"
