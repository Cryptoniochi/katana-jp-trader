"""リアルタイム取引リスク管理の共通モデル。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from app.trading.signal_models import TradeSignal


class RiskDecision(StrEnum):
    """リスク判定結果。"""

    APPROVED = "approved"
    REJECTED = "rejected"
    HALTED = "halted"


class RiskReason(StrEnum):
    """リスク判定理由。"""

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
    """リアルタイム取引のリスク上限。"""

    max_position_count: int = 5
    max_position_value: float = 1_000_000.0
    max_total_exposure: float = 5_000_000.0
    minimum_cash_balance: float = 500_000.0
    max_daily_loss: float = 100_000.0
    max_drawdown_rate: float = 0.10
    max_consecutive_losses: int = 3

    def __post_init__(self) -> None:
        """上限設定を検証する。"""

        if self.max_position_count <= 0:
            raise ValueError(
                "最大保有銘柄数は0より大きい必要があります。"
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

        if not 0.0 <= self.max_drawdown_rate <= 1.0:
            raise ValueError(
                "最大ドローダウン率は0以上1以下である必要があります。"
            )

        if self.max_consecutive_losses <= 0:
            raise ValueError(
                "最大連敗数は0より大きい必要があります。"
            )


@dataclass(frozen=True, slots=True)
class RiskPortfolioSnapshot:
    """リスク判定に必要な現在状態。"""

    trading_date: date
    cash_balance: float
    total_exposure: float
    current_equity: float
    peak_equity: float
    daily_realized_profit_loss: float
    consecutive_losses: int
    open_position_codes: frozenset[str]

    def __post_init__(self) -> None:
        """現在状態を検証する。"""

        for name, value in {
            "現金残高": self.cash_balance,
            "総投資額": self.total_exposure,
            "現在資産": self.current_equity,
            "ピーク資産": self.peak_equity,
            "連敗数": self.consecutive_losses,
        }.items():
            if value < 0:
                raise ValueError(
                    f"{name}は0以上である必要があります。"
                )

        normalized_codes = frozenset(
            code.strip()
            for code in self.open_position_codes
        )

        if any(
            not code.isdigit()
            or len(code) not in {4, 5}
            for code in normalized_codes
        ):
            raise ValueError(
                "保有銘柄コードは4桁または5桁の数字で"
                "指定してください。"
            )

        object.__setattr__(
            self,
            "open_position_codes",
            normalized_codes,
        )

    @property
    def position_count(self) -> int:
        """現在保有銘柄数を返す。"""

        return len(self.open_position_codes)

    @property
    def drawdown_rate(self) -> float:
        """ピーク資産からのドローダウン率を返す。"""

        if self.peak_equity <= 0:
            return 0.0

        return max(
            0.0,
            (
                self.peak_equity
                - self.current_equity
            )
            / self.peak_equity,
        )


@dataclass(frozen=True, slots=True)
class RiskAssessment:
    """1シグナルに対するリスク判定結果。"""

    signal: TradeSignal
    decision: RiskDecision
    reason: RiskReason
    estimated_order_value: float
    projected_total_exposure: float
    projected_cash_balance: float
    message: str

    def __post_init__(self) -> None:
        """判定結果を検証する。"""

        if self.estimated_order_value < 0:
            raise ValueError(
                "推定注文金額は0以上である必要があります。"
            )

        if self.projected_total_exposure < 0:
            raise ValueError(
                "予想総投資額は0以上である必要があります。"
            )

        if not self.message.strip():
            raise ValueError(
                "リスク判定メッセージを指定してください。"
            )

        if (
            self.decision is RiskDecision.APPROVED
            and self.reason is not RiskReason.APPROVED
        ):
            raise ValueError(
                "承認結果の理由はapprovedである必要があります。"
            )

        if (
            self.decision is not RiskDecision.APPROVED
            and self.reason is RiskReason.APPROVED
        ):
            raise ValueError(
                "拒否・停止結果にapproved理由は設定できません。"
            )

    @property
    def is_approved(self) -> bool:
        """注文許可か返す。"""

        return self.decision is RiskDecision.APPROVED

    @property
    def is_rejected(self) -> bool:
        """注文拒否か返す。"""

        return self.decision is RiskDecision.REJECTED

    @property
    def is_halted(self) -> bool:
        """緊急停止状態か返す。"""

        return self.decision is RiskDecision.HALTED
