"""LiveRiskManagerのテスト。"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from app.live.risk_manager import LiveRiskManager
from app.live.risk_models import (
    RiskLimits,
    RiskPortfolioSnapshot,
    RiskReason,
)
from app.trading.signal_models import (
    SignalAction,
    TradeSignal,
)


def create_signal(
    *,
    code: str = "7203",
    action: SignalAction = SignalAction.BUY,
    price: float = 1000.0,
    quantity: int = 100,
) -> TradeSignal:
    """テスト用シグナルを作成する。"""

    return TradeSignal(
        signal_id=(
            f"signal-{code}-{action.value}-{price}-{quantity}"
        ),
        code=code,
        strategy_name="test",
        action=action,
        generated_at=datetime(
            2026,
            7,
            17,
            tzinfo=timezone.utc,
        ),
        signal_price=price,
        quantity=quantity,
        reason="test signal",
    )


def create_portfolio(
    *,
    cash: float = 2_000_000.0,
    exposure: float = 500_000.0,
    equity: float = 2_500_000.0,
    peak: float = 2_500_000.0,
    daily_pnl: float = 0.0,
    consecutive_losses: int = 0,
    codes: frozenset[str] = frozenset(),
) -> RiskPortfolioSnapshot:
    """テスト用リスク状態を作成する。"""

    return RiskPortfolioSnapshot(
        trading_date=date(2026, 7, 17),
        cash_balance=cash,
        total_exposure=exposure,
        current_equity=equity,
        peak_equity=peak,
        daily_realized_profit_loss=daily_pnl,
        consecutive_losses=consecutive_losses,
        open_position_codes=codes,
    )


def create_limits() -> RiskLimits:
    """判定しやすい上限設定を返す。"""

    return RiskLimits(
        max_position_count=2,
        max_position_value=500_000.0,
        max_total_exposure=1_000_000.0,
        minimum_cash_balance=500_000.0,
        max_daily_loss=100_000.0,
        max_drawdown_rate=0.10,
        max_consecutive_losses=3,
    )


def test_approves_valid_buy() -> None:
    """全条件内の買いを承認する。"""

    result = LiveRiskManager(
        limits=create_limits()
    ).assess(
        create_signal(),
        portfolio=create_portfolio(),
    )

    assert result.is_approved
    assert result.reason is RiskReason.APPROVED
    assert result.estimated_order_value == 100_000.0
    assert result.projected_total_exposure == 600_000.0
    assert result.projected_cash_balance == 1_900_000.0


@pytest.mark.parametrize(
    ("portfolio", "signal_kwargs", "reason"),
    [
        (
            create_portfolio(
                codes=frozenset({"7203"})
            ),
            {},
            RiskReason.DUPLICATE_POSITION,
        ),
        (
            create_portfolio(
                codes=frozenset({"7203", "6758"})
            ),
            {"code": "9984"},
            RiskReason.MAX_POSITION_COUNT,
        ),
        (
            create_portfolio(),
            {"price": 6000.0},
            RiskReason.MAX_POSITION_VALUE,
        ),
        (
            create_portfolio(
                exposure=700_000.0
            ),
            {"price": 4000.0},
            RiskReason.MAX_TOTAL_EXPOSURE,
        ),
        (
            create_portfolio(
                cash=800_000.0,
                exposure=0.0,
            ),
            {"price": 4000.0},
            RiskReason.MINIMUM_CASH,
        ),
    ],
)
def test_rejects_entry_limits(
    portfolio: RiskPortfolioSnapshot,
    signal_kwargs: dict[str, object],
    reason: RiskReason,
) -> None:
    """各エントリー上限違反を拒否する。"""

    result = LiveRiskManager(
        limits=create_limits()
    ).assess(
        create_signal(**signal_kwargs),
        portfolio=portfolio,
    )

    assert result.is_rejected
    assert result.reason is reason


@pytest.mark.parametrize(
    ("portfolio", "reason"),
    [
        (
            create_portfolio(
                daily_pnl=-100_000.0
            ),
            RiskReason.DAILY_LOSS_LIMIT,
        ),
        (
            create_portfolio(
                equity=900_000.0,
                peak=1_000_000.0,
            ),
            RiskReason.DRAWDOWN_LIMIT,
        ),
        (
            create_portfolio(
                consecutive_losses=3
            ),
            RiskReason.CONSECUTIVE_LOSS_LIMIT,
        ),
    ],
)
def test_halts_on_loss_limits(
    portfolio: RiskPortfolioSnapshot,
    reason: RiskReason,
) -> None:
    """各損失上限到達時に停止する。"""

    result = LiveRiskManager(
        limits=create_limits()
    ).assess(
        create_signal(),
        portfolio=portfolio,
    )

    assert result.is_halted
    assert result.reason is reason


def test_manual_halt_and_resume() -> None:
    """手動停止を有効化・解除できる。"""

    manager = LiveRiskManager(
        limits=create_limits()
    )
    manager.halt("operator halt")

    halted = manager.assess(
        create_signal(),
        portfolio=create_portfolio(),
    )

    assert manager.is_halted
    assert halted.reason is RiskReason.MANUAL_HALT
    assert halted.message == "operator halt"

    manager.resume()

    assert manager.is_halted is False
    assert manager.assess(
        create_signal(),
        portfolio=create_portfolio(),
    ).is_approved


def test_exit_is_approved_during_halt() -> None:
    """停止中でも決済系シグナルを承認する。"""

    manager = LiveRiskManager(
        limits=create_limits()
    )
    manager.halt("halted")

    result = manager.assess(
        create_signal(
            action=SignalAction.EXIT,
            price=1100.0,
        ),
        portfolio=create_portfolio(
            cash=0.0,
            exposure=100_000.0,
            equity=0.0,
            peak=1_000_000.0,
            daily_pnl=-500_000.0,
            consecutive_losses=10,
            codes=frozenset({"7203"}),
        ),
    )

    assert result.is_approved
    assert result.projected_total_exposure == 0.0
    assert result.projected_cash_balance == 110_000.0


def test_models_validate_limits_and_drawdown() -> None:
    """設定検証とDD計算を確認する。"""

    with pytest.raises(ValueError):
        RiskLimits(max_position_count=0)

    with pytest.raises(ValueError):
        RiskLimits(max_drawdown_rate=1.1)

    with pytest.raises(ValueError):
        RiskLimits(max_consecutive_losses=0)

    assert create_portfolio(
        equity=800_000.0,
        peak=1_000_000.0,
    ).drawdown_rate == pytest.approx(0.20)
