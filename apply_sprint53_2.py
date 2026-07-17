from __future__ import annotations

from pathlib import Path

FILES = {
    "app/live/risk_models.py": """\
"""リアルタイム取引リスク管理の共通モデル。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from app.trading.signal_models import TradeSignal


class RiskDecision(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"
    HALTED = "halted"


class RiskReason(StrEnum):
    APPROVED = "approved"
    DUPLICATE_POSITION = "duplicate_position"
    MAX_POSITION_COUNT = "max_position_count"
    MAX_POSITION_VALUE = "max_position_value"
    MAX_TOTAL_EXPOSURE = "max_total_exposure"
    MINIMUM_CASH = "minimum_cash"
    DAILY_LOSS_LIMIT = "daily_loss_limit"
    DRAWDOWN_LIMIT = "drawdown_limit"
    CONSECUTIVE_LOSS_LIMIT = "consecutive_loss_limit"
    MANUAL_HALT = "manual_halt"


@dataclass(frozen=True, slots=True)
class RiskLimits:
    max_position_count: int = 5
    max_position_value: float = 1_000_000.0
    max_total_exposure: float = 5_000_000.0
    minimum_cash_balance: float = 500_000.0
    max_daily_loss: float = 100_000.0
    max_drawdown_rate: float = 0.10
    max_consecutive_losses: int = 3

    def __post_init__(self) -> None:
        if self.max_position_count <= 0:
            raise ValueError("最大保有銘柄数は0より大きい必要があります。")
        for name, value in {
            "1銘柄最大投資額": self.max_position_value,
            "最大総投資額": self.max_total_exposure,
            "最低現金残高": self.minimum_cash_balance,
            "日次損失上限": self.max_daily_loss,
        }.items():
            if value < 0:
                raise ValueError(f"{name}は0以上である必要があります。")
        if not 0.0 <= self.max_drawdown_rate <= 1.0:
            raise ValueError("最大ドローダウン率は0以上1以下である必要があります。")
        if self.max_consecutive_losses <= 0:
            raise ValueError("最大連敗数は0より大きい必要があります。")


@dataclass(frozen=True, slots=True)
class RiskPortfolioSnapshot:
    trading_date: date
    cash_balance: float
    total_exposure: float
    current_equity: float
    peak_equity: float
    daily_realized_profit_loss: float
    consecutive_losses: int
    open_position_codes: frozenset[str]

    def __post_init__(self) -> None:
        for name, value in {
            "現金残高": self.cash_balance,
            "総投資額": self.total_exposure,
            "現在資産": self.current_equity,
            "ピーク資産": self.peak_equity,
            "連敗数": self.consecutive_losses,
        }.items():
            if value < 0:
                raise ValueError(f"{name}は0以上である必要があります。")
        normalized = frozenset(code.strip() for code in self.open_position_codes)
        if any(not code.isdigit() or len(code) not in {4, 5} for code in normalized):
            raise ValueError("保有銘柄コードは4桁または5桁の数字で指定してください。")
        object.__setattr__(self, "open_position_codes", normalized)

    @property
    def position_count(self) -> int:
        return len(self.open_position_codes)

    @property
    def drawdown_rate(self) -> float:
        if self.peak_equity <= 0:
            return 0.0
        return max(0.0, (self.peak_equity - self.current_equity) / self.peak_equity)


@dataclass(frozen=True, slots=True)
class RiskAssessment:
    signal: TradeSignal
    decision: RiskDecision
    reason: RiskReason
    estimated_order_value: float
    projected_total_exposure: float
    projected_cash_balance: float
    message: str

    def __post_init__(self) -> None:
        if self.estimated_order_value < 0:
            raise ValueError("推定注文金額は0以上である必要があります。")
        if self.projected_total_exposure < 0:
            raise ValueError("予想総投資額は0以上である必要があります。")
        if not self.message.strip():
            raise ValueError("リスク判定メッセージを指定してください。")
        if self.decision is RiskDecision.APPROVED and self.reason is not RiskReason.APPROVED:
            raise ValueError("承認結果の理由はapprovedである必要があります。")
        if self.decision is not RiskDecision.APPROVED and self.reason is RiskReason.APPROVED:
            raise ValueError("拒否・停止結果にapproved理由は設定できません。")

    @property
    def is_approved(self) -> bool:
        return self.decision is RiskDecision.APPROVED

    @property
    def is_rejected(self) -> bool:
        return self.decision is RiskDecision.REJECTED

    @property
    def is_halted(self) -> bool:
        return self.decision is RiskDecision.HALTED
""",
    "app/live/risk_manager.py": """\
"""リアルタイム注文前のリスク判定を行う。"""

from __future__ import annotations

from app.live.risk_models import (
    RiskAssessment,
    RiskDecision,
    RiskLimits,
    RiskPortfolioSnapshot,
    RiskReason,
)
from app.trading.signal_models import SignalAction, TradeSignal


class LiveRiskManager:
    def __init__(self, *, limits: RiskLimits | None = None) -> None:
        self.limits = limits if limits is not None else RiskLimits()
        self._manual_halt = False
        self._manual_halt_reason: str | None = None

    def assess(
        self,
        signal: TradeSignal,
        *,
        portfolio: RiskPortfolioSnapshot,
    ) -> RiskAssessment:
        order_value = signal.signal_price * signal.quantity

        if signal.action in {SignalAction.SELL, SignalAction.EXIT}:
            return self._approved(
                signal,
                portfolio,
                order_value,
                "決済系シグナルはポジション縮小のため承認しました。",
            )

        if self._manual_halt:
            return self._halted(
                signal, portfolio, order_value, RiskReason.MANUAL_HALT,
                self._manual_halt_reason or "手動緊急停止が有効です。",
            )
        if portfolio.daily_realized_profit_loss <= -self.limits.max_daily_loss:
            return self._halted(
                signal, portfolio, order_value, RiskReason.DAILY_LOSS_LIMIT,
                "日次損失上限に到達しています。",
            )
        if portfolio.drawdown_rate >= self.limits.max_drawdown_rate:
            return self._halted(
                signal, portfolio, order_value, RiskReason.DRAWDOWN_LIMIT,
                "最大ドローダウン上限に到達しています。",
            )
        if portfolio.consecutive_losses >= self.limits.max_consecutive_losses:
            return self._halted(
                signal, portfolio, order_value, RiskReason.CONSECUTIVE_LOSS_LIMIT,
                "連敗数上限に到達しています。",
            )
        if signal.code in portfolio.open_position_codes:
            return self._rejected(
                signal, portfolio, order_value, RiskReason.DUPLICATE_POSITION,
                "同一銘柄の重複エントリーを拒否しました。",
            )
        if portfolio.position_count >= self.limits.max_position_count:
            return self._rejected(
                signal, portfolio, order_value, RiskReason.MAX_POSITION_COUNT,
                "最大保有銘柄数に到達しています。",
            )
        if order_value > self.limits.max_position_value:
            return self._rejected(
                signal, portfolio, order_value, RiskReason.MAX_POSITION_VALUE,
                "1銘柄あたりの最大投資額を超えています。",
            )
        if portfolio.total_exposure + order_value > self.limits.max_total_exposure:
            return self._rejected(
                signal, portfolio, order_value, RiskReason.MAX_TOTAL_EXPOSURE,
                "最大総投資額を超えています。",
            )
        if portfolio.cash_balance - order_value < self.limits.minimum_cash_balance:
            return self._rejected(
                signal, portfolio, order_value, RiskReason.MINIMUM_CASH,
                "注文後の現金残高が最低額を下回ります。",
            )
        return self._approved(
            signal, portfolio, order_value,
            "すべてのリスク条件を通過しました。",
        )

    def halt(self, reason: str = "manual emergency halt") -> None:
        normalized = reason.strip()
        if not normalized:
            raise ValueError("緊急停止理由を指定してください。")
        self._manual_halt = True
        self._manual_halt_reason = normalized

    def resume(self) -> None:
        self._manual_halt = False
        self._manual_halt_reason = None

    @property
    def is_halted(self) -> bool:
        return self._manual_halt

    @staticmethod
    def _approved(signal, portfolio, order_value, message) -> RiskAssessment:
        is_buy = signal.action is SignalAction.BUY
        return RiskAssessment(
            signal=signal,
            decision=RiskDecision.APPROVED,
            reason=RiskReason.APPROVED,
            estimated_order_value=order_value,
            projected_total_exposure=max(
                0.0,
                portfolio.total_exposure + (order_value if is_buy else -order_value),
            ),
            projected_cash_balance=(
                portfolio.cash_balance + (-order_value if is_buy else order_value)
            ),
            message=message,
        )

    @staticmethod
    def _rejected(signal, portfolio, order_value, reason, message) -> RiskAssessment:
        return RiskAssessment(
            signal=signal,
            decision=RiskDecision.REJECTED,
            reason=reason,
            estimated_order_value=order_value,
            projected_total_exposure=portfolio.total_exposure,
            projected_cash_balance=portfolio.cash_balance,
            message=message,
        )

    @staticmethod
    def _halted(signal, portfolio, order_value, reason, message) -> RiskAssessment:
        return RiskAssessment(
            signal=signal,
            decision=RiskDecision.HALTED,
            reason=reason,
            estimated_order_value=order_value,
            projected_total_exposure=portfolio.total_exposure,
            projected_cash_balance=portfolio.cash_balance,
            message=message,
        )
""",
    "tests/test_live_risk_manager.py": """\
"""LiveRiskManagerのテスト。"""

from datetime import date, datetime, timezone

import pytest

from app.live.risk_manager import LiveRiskManager
from app.live.risk_models import RiskLimits, RiskPortfolioSnapshot, RiskReason
from app.trading.signal_models import SignalAction, TradeSignal


def make_signal(
    *,
    code: str = "7203",
    action: SignalAction = SignalAction.BUY,
    price: float = 1000.0,
    quantity: int = 100,
) -> TradeSignal:
    return TradeSignal(
        signal_id=f"signal-{code}-{action.value}-{price}-{quantity}",
        code=code,
        strategy_name="test",
        action=action,
        generated_at=datetime(2026, 7, 17, tzinfo=timezone.utc),
        signal_price=price,
        quantity=quantity,
        reason="test signal",
    )


def make_portfolio(
    *,
    cash: float = 2_000_000.0,
    exposure: float = 500_000.0,
    equity: float = 2_500_000.0,
    peak: float = 2_500_000.0,
    daily_pnl: float = 0.0,
    consecutive_losses: int = 0,
    codes: frozenset[str] = frozenset(),
) -> RiskPortfolioSnapshot:
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


def make_limits() -> RiskLimits:
    return RiskLimits(
        max_position_count=2,
        max_position_value=500_000.0,
        max_total_exposure=1_000_000.0,
        minimum_cash_balance=500_000.0,
        max_daily_loss=100_000.0,
        max_drawdown_rate=0.10,
        max_consecutive_losses=3,
    )


def assess(portfolio, **signal_kwargs):
    return LiveRiskManager(limits=make_limits()).assess(
        make_signal(**signal_kwargs),
        portfolio=portfolio,
    )


def test_approves_valid_buy() -> None:
    result = assess(make_portfolio())
    assert result.is_approved
    assert result.projected_total_exposure == 600_000.0
    assert result.projected_cash_balance == 1_900_000.0


@pytest.mark.parametrize(
    ("portfolio_value", "signal_kwargs", "reason"),
    [
        (
            make_portfolio(codes=frozenset({"7203"})),
            {},
            RiskReason.DUPLICATE_POSITION,
        ),
        (
            make_portfolio(codes=frozenset({"7203", "6758"})),
            {"code": "9984"},
            RiskReason.MAX_POSITION_COUNT,
        ),
        (
            make_portfolio(),
            {"price": 6000.0},
            RiskReason.MAX_POSITION_VALUE,
        ),
        (
            make_portfolio(exposure=700_000.0),
            {"price": 4000.0},
            RiskReason.MAX_TOTAL_EXPOSURE,
        ),
        (
            make_portfolio(cash=800_000.0, exposure=0.0),
            {"price": 4000.0},
            RiskReason.MINIMUM_CASH,
        ),
    ],
)
def test_rejects_entry_limits(
    portfolio_value,
    signal_kwargs,
    reason,
) -> None:
    result = assess(portfolio_value, **signal_kwargs)
    assert result.is_rejected
    assert result.reason is reason


@pytest.mark.parametrize(
    ("portfolio_value", "reason"),
    [
        (
            make_portfolio(daily_pnl=-100_000.0),
            RiskReason.DAILY_LOSS_LIMIT,
        ),
        (
            make_portfolio(equity=900_000.0, peak=1_000_000.0),
            RiskReason.DRAWDOWN_LIMIT,
        ),
        (
            make_portfolio(consecutive_losses=3),
            RiskReason.CONSECUTIVE_LOSS_LIMIT,
        ),
    ],
)
def test_halts_on_loss_limits(portfolio_value, reason) -> None:
    result = assess(portfolio_value)
    assert result.is_halted
    assert result.reason is reason


def test_manual_halt_and_resume() -> None:
    manager = LiveRiskManager(limits=make_limits())
    manager.halt("operator halt")
    halted = manager.assess(make_signal(), portfolio=make_portfolio())
    assert halted.reason is RiskReason.MANUAL_HALT
    manager.resume()
    assert manager.assess(make_signal(), portfolio=make_portfolio()).is_approved


def test_exit_is_approved_during_halt() -> None:
    manager = LiveRiskManager(limits=make_limits())
    manager.halt("halt")
    result = manager.assess(
        make_signal(action=SignalAction.EXIT, price=1100.0),
        portfolio=make_portfolio(
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


def test_models_validate_limits_and_drawdown() -> None:
    with pytest.raises(ValueError):
        RiskLimits(max_position_count=0)
    with pytest.raises(ValueError):
        RiskLimits(max_drawdown_rate=1.1)
    assert make_portfolio(
        equity=800_000.0,
        peak=1_000_000.0,
    ).drawdown_rate == pytest.approx(0.20)
""",
}


def main() -> int:
    root = Path.cwd()
    for relative_path, content in FILES.items():
        destination = root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8", newline="\n")
        print(f"updated: {relative_path}")
    print("Sprint53-2 files were written successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
