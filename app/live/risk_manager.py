"""リアルタイム注文前のリスク判定を行う。"""

from __future__ import annotations

from app.live.risk_models import (
    RiskAssessment,
    RiskDecision,
    RiskLimits,
    RiskPortfolioSnapshot,
    RiskReason,
)
from app.trading.signal_models import (
    SignalAction,
    TradeSignal,
)


class LiveRiskManager:
    """売買シグナルを資金・損失・保有上限で判定する。"""

    def __init__(
        self,
        *,
        limits: RiskLimits | None = None,
    ) -> None:
        """リスク上限と停止状態を初期化する。"""

        self.limits = (
            limits
            if limits is not None
            else RiskLimits()
        )
        self._manual_halt = False
        self._manual_halt_reason: str | None = None

    def assess(
        self,
        signal: TradeSignal,
        *,
        portfolio: RiskPortfolioSnapshot,
    ) -> RiskAssessment:
        """シグナルを現在状態に照らして判定する。"""

        estimated_order_value = (
            signal.signal_price * signal.quantity
        )

        if signal.action in {
            SignalAction.SELL,
            SignalAction.EXIT,
        }:
            return self._approved(
                signal,
                portfolio=portfolio,
                estimated_order_value=estimated_order_value,
                message=(
                    "決済系シグナルはポジション縮小のため"
                    "リスク上限判定を通過しました。"
                ),
            )

        if self._manual_halt:
            return self._halted(
                signal,
                portfolio=portfolio,
                estimated_order_value=estimated_order_value,
                reason=RiskReason.MANUAL_HALT,
                message=(
                    self._manual_halt_reason
                    or "手動緊急停止が有効です。"
                ),
            )

        if (
            portfolio.daily_realized_profit_loss
            <= -self.limits.max_daily_loss
        ):
            return self._halted(
                signal,
                portfolio=portfolio,
                estimated_order_value=estimated_order_value,
                reason=RiskReason.DAILY_LOSS_LIMIT,
                message="日次損失上限に到達しています。",
            )

        if (
            portfolio.drawdown_rate
            >= self.limits.max_drawdown_rate
        ):
            return self._halted(
                signal,
                portfolio=portfolio,
                estimated_order_value=estimated_order_value,
                reason=RiskReason.DRAWDOWN_LIMIT,
                message="最大ドローダウン上限に到達しています。",
            )

        if (
            portfolio.consecutive_losses
            >= self.limits.max_consecutive_losses
        ):
            return self._halted(
                signal,
                portfolio=portfolio,
                estimated_order_value=estimated_order_value,
                reason=RiskReason.CONSECUTIVE_LOSS_LIMIT,
                message="連敗数上限に到達しています。",
            )

        if signal.code in portfolio.open_position_codes:
            return self._rejected(
                signal,
                portfolio=portfolio,
                estimated_order_value=estimated_order_value,
                reason=RiskReason.DUPLICATE_POSITION,
                message="同一銘柄の重複エントリーを拒否しました。",
            )

        if (
            portfolio.position_count
            >= self.limits.max_position_count
        ):
            return self._rejected(
                signal,
                portfolio=portfolio,
                estimated_order_value=estimated_order_value,
                reason=RiskReason.MAX_POSITION_COUNT,
                message="最大保有銘柄数に到達しています。",
            )

        if (
            estimated_order_value
            > self.limits.max_position_value
        ):
            return self._rejected(
                signal,
                portfolio=portfolio,
                estimated_order_value=estimated_order_value,
                reason=RiskReason.MAX_POSITION_VALUE,
                message="1銘柄あたりの最大投資額を超えています。",
            )

        projected_total_exposure = (
            portfolio.total_exposure
            + estimated_order_value
        )

        if (
            projected_total_exposure
            > self.limits.max_total_exposure
        ):
            return self._rejected(
                signal,
                portfolio=portfolio,
                estimated_order_value=estimated_order_value,
                reason=RiskReason.MAX_TOTAL_EXPOSURE,
                message="最大総投資額を超えています。",
            )

        projected_cash_balance = (
            portfolio.cash_balance
            - estimated_order_value
        )

        if (
            projected_cash_balance
            < self.limits.minimum_cash_balance
        ):
            return self._rejected(
                signal,
                portfolio=portfolio,
                estimated_order_value=estimated_order_value,
                reason=RiskReason.MINIMUM_CASH,
                message="注文後の現金残高が最低額を下回ります。",
            )

        return self._approved(
            signal,
            portfolio=portfolio,
            estimated_order_value=estimated_order_value,
            message="すべてのリスク条件を通過しました。",
        )

    def halt(
        self,
        reason: str = "manual emergency halt",
    ) -> None:
        """手動緊急停止を有効にする。"""

        normalized = reason.strip()

        if not normalized:
            raise ValueError(
                "緊急停止理由を指定してください。"
            )

        self._manual_halt = True
        self._manual_halt_reason = normalized

    def resume(self) -> None:
        """手動緊急停止を解除する。"""

        self._manual_halt = False
        self._manual_halt_reason = None

    @property
    def is_halted(self) -> bool:
        """手動緊急停止中か返す。"""

        return self._manual_halt

    @staticmethod
    def _approved(
        signal: TradeSignal,
        *,
        portfolio: RiskPortfolioSnapshot,
        estimated_order_value: float,
        message: str,
    ) -> RiskAssessment:
        """承認結果を作成する。"""

        is_buy = signal.action is SignalAction.BUY

        return RiskAssessment(
            signal=signal,
            decision=RiskDecision.APPROVED,
            reason=RiskReason.APPROVED,
            estimated_order_value=estimated_order_value,
            projected_total_exposure=max(
                0.0,
                portfolio.total_exposure
                + (
                    estimated_order_value
                    if is_buy
                    else -estimated_order_value
                ),
            ),
            projected_cash_balance=(
                portfolio.cash_balance
                + (
                    -estimated_order_value
                    if is_buy
                    else estimated_order_value
                )
            ),
            message=message,
        )

    @staticmethod
    def _rejected(
        signal: TradeSignal,
        *,
        portfolio: RiskPortfolioSnapshot,
        estimated_order_value: float,
        reason: RiskReason,
        message: str,
    ) -> RiskAssessment:
        """拒否結果を作成する。"""

        return RiskAssessment(
            signal=signal,
            decision=RiskDecision.REJECTED,
            reason=reason,
            estimated_order_value=estimated_order_value,
            projected_total_exposure=portfolio.total_exposure,
            projected_cash_balance=portfolio.cash_balance,
            message=message,
        )

    @staticmethod
    def _halted(
        signal: TradeSignal,
        *,
        portfolio: RiskPortfolioSnapshot,
        estimated_order_value: float,
        reason: RiskReason,
        message: str,
    ) -> RiskAssessment:
        """緊急停止結果を作成する。"""

        return RiskAssessment(
            signal=signal,
            decision=RiskDecision.HALTED,
            reason=reason,
            estimated_order_value=estimated_order_value,
            projected_total_exposure=portfolio.total_exposure,
            projected_cash_balance=portfolio.cash_balance,
            message=message,
        )
