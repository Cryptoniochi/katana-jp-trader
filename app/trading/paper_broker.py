"""実資金を使わずに注文・約定・ポジションを再現するPaper Broker。"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone

from app.trading.broker_adapter import (
    BrokerAccountSnapshot,
    BrokerAdapter,
    BrokerOrderNotFoundError,
    BrokerOrderRejectedError,
    BrokerOrderSnapshot,
    BrokerPosition,
    BrokerPositionSide,
    BrokerRequestError,
)
from app.trading.order_models import (
    OrderSide,
    OrderStatus,
    OrderType,
    TradeOrder,
)


@dataclass(frozen=True, slots=True)
class PaperBrokerSettings:
    """Paper Brokerの初期資金と約定条件。"""

    initial_cash: float = 10_000_000.0
    commission_per_order: float = 0.0
    slippage_rate: float = 0.0
    currency: str = "JPY"
    broker_name: str = "paper"

    def __post_init__(self) -> None:
        """不正な設定を拒否して文字列を正規化する。"""

        normalized_currency = self.currency.strip().upper()
        normalized_broker_name = self.broker_name.strip()

        if self.initial_cash < 0:
            raise ValueError(
                "初期資金は0以上である必要があります。"
            )

        if self.commission_per_order < 0:
            raise ValueError(
                "注文手数料は0以上である必要があります。"
            )

        if self.slippage_rate < 0:
            raise ValueError(
                "スリッページ率は0以上である必要があります。"
            )

        if not normalized_currency:
            raise ValueError(
                "通貨コードを指定してください。"
            )

        if (
            len(normalized_currency) != 3
            or not normalized_currency.isalpha()
        ):
            raise ValueError(
                "通貨コードは英字3文字で指定してください。"
            )

        if not normalized_broker_name:
            raise ValueError(
                "Broker名を指定してください。"
            )

        object.__setattr__(
            self,
            "currency",
            normalized_currency,
        )
        object.__setattr__(
            self,
            "broker_name",
            normalized_broker_name,
        )


@dataclass(slots=True)
class _PaperOrderState:
    """Paper Broker内部の注文状態。"""

    order: TradeOrder
    broker_order_id: str
    status: OrderStatus
    filled_quantity: int
    average_fill_price: float | None
    submitted_at: datetime
    updated_at: datetime
    status_reason: str | None = None


@dataclass(slots=True)
class _PaperPositionState:
    """Paper Broker内部のポジション状態。"""

    code: str
    side: BrokerPositionSide
    quantity: int
    average_price: float
    market_price: float
    updated_at: datetime


class PaperBroker:
    """成行注文を即時約定させるインメモリBroker。"""

    def __init__(
        self,
        *,
        settings: PaperBrokerSettings | None = None,
        price_provider: Callable[[str], float],
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        """設定・現在価格取得処理・時計を受け取る。"""

        self.settings = (
            settings
            if settings is not None
            else PaperBrokerSettings()
        )
        self.price_provider = price_provider
        self.now_provider = (
            now_provider
            if now_provider is not None
            else lambda: datetime.now(timezone.utc)
        )

        self._cash_balance = self.settings.initial_cash

        self._orders: dict[
            str,
            _PaperOrderState,
        ] = {}

        self._client_order_ids: dict[
            str,
            str,
        ] = {}

        self._positions: dict[
            tuple[
                str,
                BrokerPositionSide,
            ],
            _PaperPositionState,
        ] = {}

        self._next_broker_order_number = 1

    @property
    def broker_name(self) -> str:
        """Broker名を返す。"""

        return self.settings.broker_name

    def submit_order(
        self,
        order: TradeOrder,
    ) -> BrokerOrderSnapshot:
        """成行注文を即時約定させる。"""

        existing_broker_order_id = (
            self._client_order_ids.get(
                order.order_id,
            )
        )

        if existing_broker_order_id is not None:
            return self.get_order(
                existing_broker_order_id,
            )

        if order.order_type is not OrderType.MARKET:
            raise BrokerRequestError(
                "現在のPaper Brokerは"
                "成行注文だけをサポートします。 "
                f"order_type={order.order_type.value}"
            )

        current_time = self._current_time()
        market_price = self._get_market_price(
            order.code,
        )
        fill_price = self._calculate_fill_price(
            side=order.side,
            market_price=market_price,
        )

        self._validate_execution(
            order=order,
            fill_price=fill_price,
        )

        broker_order_id = self._create_broker_order_id()

        state = _PaperOrderState(
            order=order,
            broker_order_id=broker_order_id,
            status=OrderStatus.SENT,
            filled_quantity=0,
            average_fill_price=None,
            submitted_at=current_time,
            updated_at=current_time,
        )

        self._orders[
            broker_order_id
        ] = state
        self._client_order_ids[
            order.order_id
        ] = broker_order_id

        try:
            self._apply_fill(
                state=state,
                fill_price=fill_price,
                filled_at=current_time,
            )

        except Exception:
            self._orders.pop(
                broker_order_id,
                None,
            )
            self._client_order_ids.pop(
                order.order_id,
                None,
            )
            raise

        return self._to_snapshot(
            state,
        )

    def cancel_order(
        self,
        broker_order_id: str,
    ) -> BrokerOrderSnapshot:
        """未完了注文を取り消す。"""

        state = self._get_state(
            broker_order_id,
        )

        if state.status.is_terminal:
            raise BrokerRequestError(
                "終了済み注文は取り消せません。 "
                f"broker_order_id={state.broker_order_id} "
                f"status={state.status.value}"
            )

        current_time = self._current_time()

        state.status = OrderStatus.CANCELLED
        state.updated_at = current_time
        state.status_reason = "cancelled by client"

        return self._to_snapshot(
            state,
        )

    def get_order(
        self,
        broker_order_id: str,
    ) -> BrokerOrderSnapshot:
        """Broker注文の最新状態を返す。"""

        return self._to_snapshot(
            self._get_state(
                broker_order_id,
            )
        )

    def list_orders(
        self,
        *,
        active_only: bool = False,
    ) -> list[BrokerOrderSnapshot]:
        """Broker注文一覧を新しい順に返す。"""

        states = list(
            self._orders.values()
        )

        if active_only:
            states = [
                state
                for state in states
                if not state.status.is_terminal
            ]

        return [
            self._to_snapshot(
                state,
            )
            for state in sorted(
                states,
                key=lambda item: (
                    item.submitted_at,
                    item.broker_order_id,
                ),
                reverse=True,
            )
        ]

    def list_positions(
        self,
    ) -> list[BrokerPosition]:
        """現在保有しているポジション一覧を返す。"""

        return [
            BrokerPosition(
                code=state.code,
                side=state.side,
                quantity=state.quantity,
                average_price=state.average_price,
                market_price=state.market_price,
                updated_at=state.updated_at,
            )
            for state in sorted(
                self._positions.values(),
                key=lambda item: (
                    item.code,
                    item.side.value,
                ),
            )
            if state.quantity > 0
        ]

    def get_account(
        self,
    ) -> BrokerAccountSnapshot:
        """現金・時価総額・純資産額を返す。"""

        current_time = self._current_time()
        market_value = sum(
            position.market_price
            * position.quantity
            for position in self._positions.values()
            if position.side is BrokerPositionSide.LONG
        )

        short_market_value = sum(
            position.market_price
            * position.quantity
            for position in self._positions.values()
            if position.side is BrokerPositionSide.SHORT
        )

        equity = (
            self._cash_balance
            + market_value
            - short_market_value
        )

        return BrokerAccountSnapshot(
            currency=self.settings.currency,
            cash_balance=self._cash_balance,
            buying_power=self._cash_balance,
            market_value=(
                market_value
                + short_market_value
            ),
            equity=equity,
            updated_at=current_time,
        )

    def update_market_price(
        self,
        code: str,
        market_price: float,
    ) -> None:
        """保有ポジションの現在価格を更新する。"""

        normalized_code = self._normalize_code(
            code,
        )

        if market_price <= 0:
            raise ValueError(
                "現在価格は0より大きい必要があります。"
            )

        current_time = self._current_time()

        for (
            position_code,
            _position_side,
        ), position in self._positions.items():
            if position_code != normalized_code:
                continue

            position.market_price = market_price
            position.updated_at = current_time

    def _apply_fill(
        self,
        *,
        state: _PaperOrderState,
        fill_price: float,
        filled_at: datetime,
    ) -> None:
        """注文を全約定させ、資金とポジションへ反映する。"""

        order = state.order
        gross_amount = (
            fill_price
            * order.quantity
        )
        commission = (
            self.settings.commission_per_order
        )

        if order.side is OrderSide.BUY:
            total_cost = (
                gross_amount
                + commission
            )

            if total_cost > self._cash_balance:
                raise BrokerOrderRejectedError(
                    "買付余力が不足しています。 "
                    f"required={total_cost} "
                    f"available={self._cash_balance}"
                )

            self._cash_balance -= total_cost

            self._increase_position(
                code=order.code,
                side=BrokerPositionSide.LONG,
                quantity=order.quantity,
                fill_price=fill_price,
                filled_at=filled_at,
            )

        else:
            self._execute_sell(
                code=order.code,
                quantity=order.quantity,
                fill_price=fill_price,
                commission=commission,
                filled_at=filled_at,
            )

        state.status = OrderStatus.FILLED
        state.filled_quantity = order.quantity
        state.average_fill_price = fill_price
        state.updated_at = filled_at
        state.status_reason = "paper market fill"

    def _execute_sell(
        self,
        *,
        code: str,
        quantity: int,
        fill_price: float,
        commission: float,
        filled_at: datetime,
    ) -> None:
        """買いポジションを売却する。"""

        position_key = (
            code,
            BrokerPositionSide.LONG,
        )

        position = self._positions.get(
            position_key,
        )

        if (
            position is None
            or position.quantity < quantity
        ):
            available_quantity = (
                position.quantity
                if position is not None
                else 0
            )

            raise BrokerOrderRejectedError(
                "売却可能数量が不足しています。 "
                f"code={code} "
                f"required={quantity} "
                f"available={available_quantity}"
            )

        proceeds = (
            fill_price
            * quantity
            - commission
        )

        self._cash_balance += proceeds
        position.quantity -= quantity
        position.market_price = fill_price
        position.updated_at = filled_at

        if position.quantity == 0:
            del self._positions[
                position_key
            ]

    def _increase_position(
        self,
        *,
        code: str,
        side: BrokerPositionSide,
        quantity: int,
        fill_price: float,
        filled_at: datetime,
    ) -> None:
        """同方向ポジションを加重平均で増加させる。"""

        position_key = (
            code,
            side,
        )

        existing = self._positions.get(
            position_key,
        )

        if existing is None:
            self._positions[
                position_key
            ] = _PaperPositionState(
                code=code,
                side=side,
                quantity=quantity,
                average_price=fill_price,
                market_price=fill_price,
                updated_at=filled_at,
            )
            return

        total_quantity = (
            existing.quantity
            + quantity
        )

        weighted_average = (
            existing.average_price
            * existing.quantity
            + fill_price
            * quantity
        ) / total_quantity

        existing.quantity = total_quantity
        existing.average_price = weighted_average
        existing.market_price = fill_price
        existing.updated_at = filled_at

    def _validate_execution(
        self,
        *,
        order: TradeOrder,
        fill_price: float,
    ) -> None:
        """注文の約定可否を事前検証する。"""

        if order.side is OrderSide.BUY:
            required_cash = (
                fill_price
                * order.quantity
                + self.settings.commission_per_order
            )

            if required_cash > self._cash_balance:
                raise BrokerOrderRejectedError(
                    "買付余力が不足しています。 "
                    f"required={required_cash} "
                    f"available={self._cash_balance}"
                )
            return

        position = self._positions.get(
            (
                order.code,
                BrokerPositionSide.LONG,
            )
        )

        available_quantity = (
            position.quantity
            if position is not None
            else 0
        )

        if available_quantity < order.quantity:
            raise BrokerOrderRejectedError(
                "売却可能数量が不足しています。 "
                f"code={order.code} "
                f"required={order.quantity} "
                f"available={available_quantity}"
            )

    def _calculate_fill_price(
        self,
        *,
        side: OrderSide,
        market_price: float,
    ) -> float:
        """スリッページを反映した約定価格を返す。"""

        if side is OrderSide.BUY:
            return market_price * (
                1.0
                + self.settings.slippage_rate
            )

        return market_price * (
            1.0
            - self.settings.slippage_rate
        )

    def _get_market_price(
        self,
        code: str,
    ) -> float:
        """現在価格を取得して検証する。"""

        normalized_code = self._normalize_code(
            code,
        )

        try:
            price = float(
                self.price_provider(
                    normalized_code,
                )
            )

        except Exception as error:
            raise BrokerRequestError(
                "現在価格を取得できませんでした。 "
                f"code={normalized_code}"
            ) from error

        if price <= 0:
            raise BrokerRequestError(
                "現在価格は0より大きい必要があります。 "
                f"code={normalized_code} "
                f"price={price}"
            )

        return price

    def _get_state(
        self,
        broker_order_id: str,
    ) -> _PaperOrderState:
        """Broker注文IDに対応する内部状態を返す。"""

        normalized_broker_order_id = (
            broker_order_id.strip()
        )

        if not normalized_broker_order_id:
            raise ValueError(
                "Broker注文IDを指定してください。"
            )

        state = self._orders.get(
            normalized_broker_order_id,
        )

        if state is None:
            raise BrokerOrderNotFoundError(
                "指定されたPaper注文が存在しません。 "
                f"broker_order_id="
                f"{normalized_broker_order_id}"
            )

        return state

    def _create_broker_order_id(
        self,
    ) -> str:
        """連番のPaper注文IDを生成する。"""

        broker_order_id = (
            "paper-order-"
            f"{self._next_broker_order_number:08d}"
        )

        self._next_broker_order_number += 1

        return broker_order_id

    def _current_time(
        self,
    ) -> datetime:
        """UTCの現在日時を返す。"""

        current_time = self.now_provider()

        if current_time.tzinfo is None:
            raise ValueError(
                "現在日時にはタイムゾーンが必要です。"
            )

        return current_time.astimezone(
            timezone.utc,
        )

    @staticmethod
    def _normalize_code(
        code: str,
    ) -> str:
        """銘柄コードを検証して正規化する。"""

        normalized_code = code.strip()

        if not normalized_code:
            raise ValueError(
                "銘柄コードを指定してください。"
            )

        if not normalized_code.isdigit():
            raise ValueError(
                "銘柄コードは数字で指定してください。"
            )

        if len(normalized_code) not in {
            4,
            5,
        }:
            raise ValueError(
                "銘柄コードは4桁または5桁で"
                "指定してください。"
            )

        return normalized_code

    @staticmethod
    def _to_snapshot(
        state: _PaperOrderState,
    ) -> BrokerOrderSnapshot:
        """内部注文状態を公開Snapshotへ変換する。"""

        return BrokerOrderSnapshot(
            broker_order_id=(
                state.broker_order_id
            ),
            client_order_id=(
                state.order.order_id
            ),
            code=state.order.code,
            side=state.order.side,
            status=state.status,
            quantity=state.order.quantity,
            filled_quantity=(
                state.filled_quantity
            ),
            average_fill_price=(
                state.average_fill_price
            ),
            submitted_at=(
                state.submitted_at
            ),
            updated_at=state.updated_at,
            status_reason=(
                state.status_reason
            ),
        )


def ensure_broker_adapter(
    broker: BrokerAdapter,
) -> BrokerAdapter:
    """型検査用途としてBrokerAdapterをそのまま返す。"""

    return broker