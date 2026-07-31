"""Paper Trading本番経路のFail-Closed事前リスク判定。"""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable
from typing import Protocol

from app.trading.signal_models import SignalAction, TradeSignal


class PaperBrokerRiskView(Protocol):
    """事前リスク判定に必要なPaper Broker情報。"""

    def get_account(self):
        """口座状態を返す。"""

    def list_positions(self):
        """保有ポジションを返す。"""


@dataclass(frozen=True, slots=True)
class PaperTradingRiskLimits:
    """Paper Tradingの強制リスク上限。"""

    max_position_count: int = 5
    max_position_value: float = 1_000_000.0
    max_total_exposure: float = 5_000_000.0
    minimum_cash_balance: float = 500_000.0
    max_daily_loss: float = 100_000.0
    max_daily_entries: int = 5

    def __post_init__(self) -> None:
        if self.max_position_count <= 0:
            raise ValueError(
                "最大保有銘柄数は0より大きい必要があります。"
            )
        if self.max_daily_entries <= 0:
            raise ValueError(
                "1日最大エントリー数は0より大きい必要があります。"
            )
        for name, value in {
            "1銘柄最大投資額": self.max_position_value,
            "最大総投資額": self.max_total_exposure,
            "最低現金残高": self.minimum_cash_balance,
            "日次損失上限": self.max_daily_loss,
        }.items():
            if value < 0:
                raise ValueError(
                    f"{name}は0以上である必要があります。"
                )


@dataclass(frozen=True, slots=True)
class PaperTradingRiskDecision:
    """RiskAwareQueueExecutionServiceへ渡す判定結果。"""

    allows_new_entries: bool
    is_blocked: bool
    reason: str
    daily_profit_loss: float
    position_count: int
    total_exposure: float
    cash_balance: float
    proposed_order_value: float
    daily_entry_count: int

    def __post_init__(self) -> None:
        if self.allows_new_entries == self.is_blocked:
            raise ValueError(
                "allows_new_entriesとis_blockedが矛盾しています。"
            )


class PaperTradingPreTradeRiskProvider:
    """各シグナルをBroker送信直前に必ず評価する。"""

    def __init__(
        self,
        *,
        broker: PaperBrokerRiskView,
        limits: PaperTradingRiskLimits,
        on_decision: Callable[
            [TradeSignal, PaperTradingRiskDecision],
            None,
        ] | None = None,
    ) -> None:
        self.broker = broker
        self.limits = limits
        self.on_decision = on_decision
        self._initial_equity = float(
            broker.get_account().equity
        )
        self._pending_signal: TradeSignal | None = None
        self._pending_price: float | None = None
        self._daily_entry_count = 0
        self._evaluation_count = 0
        self._blocked_count = 0
        self._last_decision: (
            PaperTradingRiskDecision | None
        ) = None

    @property
    def evaluation_count(self) -> int:
        return self._evaluation_count

    @property
    def blocked_count(self) -> int:
        return self._blocked_count

    @property
    def last_decision(
        self,
    ) -> PaperTradingRiskDecision | None:
        return self._last_decision

    def prepare(
        self,
        signal: TradeSignal,
        current_price: float,
    ) -> None:
        """次にBrokerへ送るシグナルを登録する。"""

        if current_price <= 0:
            raise ValueError(
                "事前リスク判定価格は0より大きい必要があります。"
            )
        self._pending_signal = signal
        self._pending_price = float(current_price)

    def __call__(self) -> PaperTradingRiskDecision:
        """登録済みシグナルをFail-Closedで評価する。"""

        signal = self._pending_signal
        price = self._pending_price

        if signal is None or price is None:
            raise RuntimeError(
                "Risk Gateへシグナルが準備されていません。"
            )

        self._pending_signal = None
        self._pending_price = None
        self._evaluation_count += 1

        account = self.broker.get_account()
        positions = tuple(self.broker.list_positions())
        daily_profit_loss = (
            float(account.equity) - self._initial_equity
        )
        total_exposure = sum(
            abs(
                float(position.market_price)
                * int(position.quantity)
            )
            for position in positions
        )
        proposed_order_value = (
            float(price) * int(signal.quantity)
        )

        # EXITは損失上限到達後も許可し、保有解消を妨げない。
        if signal.action is SignalAction.EXIT:
            return self._record(
                allowed=True,
                reason="exit_order_allowed",
                daily_profit_loss=daily_profit_loss,
                position_count=len(positions),
                total_exposure=total_exposure,
                cash_balance=float(account.cash_balance),
                proposed_order_value=proposed_order_value,
            )

        blocked_reason: str | None = None

        if daily_profit_loss <= -self.limits.max_daily_loss:
            blocked_reason = "max_daily_loss_reached"
        elif self._daily_entry_count >= self.limits.max_daily_entries:
            blocked_reason = "max_daily_entries_reached"
        elif any(
            position.code == signal.code
            for position in positions
        ):
            blocked_reason = "duplicate_symbol_position"
        elif len(positions) >= self.limits.max_position_count:
            blocked_reason = "max_position_count_reached"
        elif proposed_order_value > self.limits.max_position_value:
            blocked_reason = "max_position_value_exceeded"
        elif (
            total_exposure + proposed_order_value
            > self.limits.max_total_exposure
        ):
            blocked_reason = "max_total_exposure_exceeded"
        elif (
            float(account.cash_balance)
            - proposed_order_value
            < self.limits.minimum_cash_balance
        ):
            blocked_reason = "minimum_cash_balance_breached"

        if blocked_reason is not None:
            return self._record(
                allowed=False,
                reason=blocked_reason,
                daily_profit_loss=daily_profit_loss,
                position_count=len(positions),
                total_exposure=total_exposure,
                cash_balance=float(account.cash_balance),
                proposed_order_value=proposed_order_value,
            )

        self._daily_entry_count += 1
        return self._record(
            allowed=True,
            reason="entry_allowed",
            daily_profit_loss=daily_profit_loss,
            position_count=len(positions),
            total_exposure=total_exposure,
            cash_balance=float(account.cash_balance),
            proposed_order_value=proposed_order_value,
        )

    def _record(
        self,
        *,
        allowed: bool,
        reason: str,
        daily_profit_loss: float,
        position_count: int,
        total_exposure: float,
        cash_balance: float,
        proposed_order_value: float,
    ) -> PaperTradingRiskDecision:
        decision = PaperTradingRiskDecision(
            allows_new_entries=allowed,
            is_blocked=not allowed,
            reason=reason,
            daily_profit_loss=daily_profit_loss,
            position_count=position_count,
            total_exposure=total_exposure,
            cash_balance=cash_balance,
            proposed_order_value=proposed_order_value,
            daily_entry_count=self._daily_entry_count,
        )
        self._last_decision = decision
        if decision.is_blocked:
            self._blocked_count += 1

        if self.on_decision is not None:
            self.on_decision(signal, decision)

        return decision
