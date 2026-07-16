"""売買シグナルを執行する前の口座・ポジションリスクを判定する。"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from app.trading.broker_adapter import (
    BrokerAccountSnapshot,
    BrokerPosition,
    BrokerPositionSide,
)
from app.trading.signal_models import (
    SignalAction,
    TradeSignal,
)


class ExecutionRiskBrokerReader(Protocol):
    """執行前リスク判定で利用するBroker情報取得インターフェース。"""

    def list_positions(
        self,
    ) -> list[BrokerPosition]:
        """現在の保有ポジション一覧を返す。"""

    def get_account(
        self,
    ) -> BrokerAccountSnapshot:
        """現在の口座情報を返す。"""


class ExecutionRiskDecision(StrEnum):
    """執行前リスク判定結果。"""

    APPROVED = "approved"
    REJECTED = "rejected"
    FAILED = "failed"


class ExecutionRiskReason(StrEnum):
    """執行を拒否した理由。"""

    ORDER_VALUE_LIMIT = "order_value_limit"
    CASH_RESERVE_LIMIT = "cash_reserve_limit"
    POSITION_COUNT_LIMIT = "position_count_limit"
    CODE_EXPOSURE_LIMIT = "code_exposure_limit"
    TOTAL_EXPOSURE_LIMIT = "total_exposure_limit"
    EXISTING_LONG_POSITION = "existing_long_position"
    INSUFFICIENT_SELL_QUANTITY = "insufficient_sell_quantity"


@dataclass(frozen=True, slots=True)
class ExecutionRiskPolicy:
    """執行前に適用するリスク制限。"""

    max_order_value: float | None = 1_000_000.0
    minimum_cash_reserve: float = 500_000.0

    max_position_count: int | None = 5
    max_code_market_value: float | None = 2_000_000.0
    max_total_market_value: float | None = 5_000_000.0

    allow_additional_buy: bool = False

    def __post_init__(self) -> None:
        """不正なリスク条件を拒否する。"""

        if (
            self.max_order_value is not None
            and self.max_order_value <= 0
        ):
            raise ValueError(
                "最大注文金額は0より大きい必要があります。"
            )

        if self.minimum_cash_reserve < 0:
            raise ValueError(
                "最低現金残高は0以上である必要があります。"
            )

        if (
            self.max_position_count is not None
            and self.max_position_count <= 0
        ):
            raise ValueError(
                "最大保有銘柄数は0より大きい必要があります。"
            )

        if (
            self.max_code_market_value is not None
            and self.max_code_market_value <= 0
        ):
            raise ValueError(
                "1銘柄最大時価は0より大きい必要があります。"
            )

        if (
            self.max_total_market_value is not None
            and self.max_total_market_value <= 0
        ):
            raise ValueError(
                "口座最大保有時価は0より大きい必要があります。"
            )


@dataclass(frozen=True, slots=True)
class ExecutionRiskResult:
    """1件のシグナルに対する執行前リスク判定結果。"""

    decision: ExecutionRiskDecision
    signal: TradeSignal

    estimated_order_value: float
    estimated_cash_after: float
    estimated_code_market_value: float
    estimated_total_market_value: float

    reasons: tuple[
        ExecutionRiskReason,
        ...
    ]
    message: str | None

    @property
    def is_approved(self) -> bool:
        """執行を許可されたか返す。"""

        return (
            self.decision
            is ExecutionRiskDecision.APPROVED
        )

    @property
    def is_rejected(self) -> bool:
        """リスク条件で拒否されたか返す。"""

        return (
            self.decision
            is ExecutionRiskDecision.REJECTED
        )

    @property
    def is_failed(self) -> bool:
        """判定処理自体が失敗したか返す。"""

        return (
            self.decision
            is ExecutionRiskDecision.FAILED
        )


class ExecutionRiskService:
    """Broker口座とポジションを基に執行可否を判定する。"""

    def __init__(
        self,
        *,
        broker: ExecutionRiskBrokerReader,
        policy: ExecutionRiskPolicy | None = None,
    ) -> None:
        """Brokerとリスク条件を設定する。"""

        self.broker = broker
        self.policy = (
            policy
            if policy is not None
            else ExecutionRiskPolicy()
        )

    def evaluate(
        self,
        signal: TradeSignal,
        *,
        continue_on_error: bool = False,
    ) -> ExecutionRiskResult:
        """シグナルの執行可否を判定する。"""

        try:
            account = self.broker.get_account()
            positions = self.broker.list_positions()

            return self._evaluate_with_snapshot(
                signal=signal,
                account=account,
                positions=positions,
            )

        except Exception as error:
            if not continue_on_error:
                raise

            return ExecutionRiskResult(
                decision=ExecutionRiskDecision.FAILED,
                signal=signal,
                estimated_order_value=0.0,
                estimated_cash_after=0.0,
                estimated_code_market_value=0.0,
                estimated_total_market_value=0.0,
                reasons=(),
                message=str(error),
            )

    def _evaluate_with_snapshot(
        self,
        *,
        signal: TradeSignal,
        account: BrokerAccountSnapshot,
        positions: list[BrokerPosition],
    ) -> ExecutionRiskResult:
        """取得済み口座情報からリスク判定する。"""

        estimated_order_value = (
            signal.signal_price
            * signal.quantity
        )

        code_long_position = self._find_position(
            positions=positions,
            code=signal.code,
            side=BrokerPositionSide.LONG,
        )

        current_code_market_value = (
            code_long_position.market_value
            if (
                code_long_position is not None
                and code_long_position.market_value is not None
            )
            else (
                code_long_position.acquisition_value
                if code_long_position is not None
                else 0.0
            )
        )

        reasons: list[
            ExecutionRiskReason
        ] = []

        if signal.action is SignalAction.BUY:
            estimated_cash_after = (
                account.cash_balance
                - estimated_order_value
            )

            estimated_code_market_value = (
                current_code_market_value
                + estimated_order_value
            )

            estimated_total_market_value = (
                account.market_value
                + estimated_order_value
            )

            self._evaluate_buy(
                signal=signal,
                positions=positions,
                code_long_position=code_long_position,
                estimated_order_value=estimated_order_value,
                estimated_cash_after=estimated_cash_after,
                estimated_code_market_value=(
                    estimated_code_market_value
                ),
                estimated_total_market_value=(
                    estimated_total_market_value
                ),
                reasons=reasons,
            )

        else:
            estimated_cash_after = (
                account.cash_balance
                + estimated_order_value
            )

            estimated_code_market_value = max(
                0.0,
                current_code_market_value
                - estimated_order_value,
            )

            estimated_total_market_value = max(
                0.0,
                account.market_value
                - estimated_order_value,
            )

            self._evaluate_sell(
                signal=signal,
                code_long_position=code_long_position,
                reasons=reasons,
            )

        if reasons:
            return ExecutionRiskResult(
                decision=ExecutionRiskDecision.REJECTED,
                signal=signal,
                estimated_order_value=estimated_order_value,
                estimated_cash_after=estimated_cash_after,
                estimated_code_market_value=(
                    estimated_code_market_value
                ),
                estimated_total_market_value=(
                    estimated_total_market_value
                ),
                reasons=tuple(
                    reasons
                ),
                message=self._create_rejection_message(
                    reasons
                ),
            )

        return ExecutionRiskResult(
            decision=ExecutionRiskDecision.APPROVED,
            signal=signal,
            estimated_order_value=estimated_order_value,
            estimated_cash_after=estimated_cash_after,
            estimated_code_market_value=(
                estimated_code_market_value
            ),
            estimated_total_market_value=(
                estimated_total_market_value
            ),
            reasons=(),
            message=None,
        )

    def _evaluate_buy(
        self,
        *,
        signal: TradeSignal,
        positions: list[BrokerPosition],
        code_long_position: BrokerPosition | None,
        estimated_order_value: float,
        estimated_cash_after: float,
        estimated_code_market_value: float,
        estimated_total_market_value: float,
        reasons: list[ExecutionRiskReason],
    ) -> None:
        """買いシグナルのリスク条件を判定する。"""

        if (
            self.policy.max_order_value is not None
            and estimated_order_value
            > self.policy.max_order_value
        ):
            reasons.append(
                ExecutionRiskReason.ORDER_VALUE_LIMIT
            )

        if (
            estimated_cash_after
            < self.policy.minimum_cash_reserve
        ):
            reasons.append(
                ExecutionRiskReason.CASH_RESERVE_LIMIT
            )

        if (
            code_long_position is not None
            and not self.policy.allow_additional_buy
        ):
            reasons.append(
                ExecutionRiskReason.EXISTING_LONG_POSITION
            )

        long_position_codes = {
            position.code
            for position in positions
            if (
                position.side
                is BrokerPositionSide.LONG
                and position.quantity > 0
            )
        }

        creates_new_position = (
            signal.code
            not in long_position_codes
        )

        if (
            creates_new_position
            and self.policy.max_position_count is not None
            and len(long_position_codes)
            >= self.policy.max_position_count
        ):
            reasons.append(
                ExecutionRiskReason.POSITION_COUNT_LIMIT
            )

        if (
            self.policy.max_code_market_value is not None
            and estimated_code_market_value
            > self.policy.max_code_market_value
        ):
            reasons.append(
                ExecutionRiskReason.CODE_EXPOSURE_LIMIT
            )

        if (
            self.policy.max_total_market_value is not None
            and estimated_total_market_value
            > self.policy.max_total_market_value
        ):
            reasons.append(
                ExecutionRiskReason.TOTAL_EXPOSURE_LIMIT
            )

    @staticmethod
    def _evaluate_sell(
        *,
        signal: TradeSignal,
        code_long_position: BrokerPosition | None,
        reasons: list[ExecutionRiskReason],
    ) -> None:
        """売り・決済シグナルの売却可能数量を判定する。"""

        available_quantity = (
            code_long_position.quantity
            if code_long_position is not None
            else 0
        )

        if available_quantity < signal.quantity:
            reasons.append(
                ExecutionRiskReason.INSUFFICIENT_SELL_QUANTITY
            )

    @staticmethod
    def _find_position(
        *,
        positions: list[BrokerPosition],
        code: str,
        side: BrokerPositionSide,
    ) -> BrokerPosition | None:
        """指定銘柄・方向のポジションを返す。"""

        for position in positions:
            if (
                position.code == code
                and position.side is side
            ):
                return position

        return None

    @staticmethod
    def _create_rejection_message(
        reasons: list[ExecutionRiskReason],
    ) -> str:
        """拒否理由一覧をメッセージへ変換する。"""

        return (
            "執行前リスク条件により拒否されました。 "
            "reasons="
            + ",".join(
                reason.value
                for reason in reasons
            )
        )