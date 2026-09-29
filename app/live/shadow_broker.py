"""外部送信せず注文計画だけを永続化するShadow Broker。"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from threading import RLock

from app.trading.broker_adapter import (
    BrokerAccountSnapshot,
    BrokerOrderNotFoundError,
    BrokerOrderSnapshot,
    BrokerPosition,
)
from app.trading.order_models import (
    OrderSide,
    OrderStatus,
    OrderType,
    TradeOrder,
)


class ShadowLedgerError(RuntimeError):
    """Shadow注文台帳の読書きに失敗した。"""


class ShadowOrderConflictError(RuntimeError):
    """同じ注文IDに異なる注文内容が指定された。"""


class ShadowOrderRecordDecision(StrEnum):
    """Shadow注文計画を記録した結果。"""

    RECORDED = "recorded"
    EXISTING = "existing"


@dataclass(frozen=True, slots=True)
class ShadowOrderRecordResult:
    """Shadow注文計画の記録結果。"""

    decision: ShadowOrderRecordDecision
    order: TradeOrder
    idempotency_key: str
    snapshot: BrokerOrderSnapshot

    @property
    def was_recorded(self) -> bool:
        """新しい注文計画を記録したか返す。"""

        return (
            self.decision
            is ShadowOrderRecordDecision.RECORDED
        )

    @property
    def was_existing(self) -> bool:
        """既存の注文計画を再利用したか返す。"""

        return (
            self.decision
            is ShadowOrderRecordDecision.EXISTING
        )


@dataclass(frozen=True, slots=True)
class ShadowBrokerSettings:
    """Shadow Brokerの永続化・口座表示設定。"""

    ledger_path: Path = Path(
        "reports/live/shadow_orders.jsonl"
    )
    initial_cash: float = 10_000_000.0
    currency: str = "JPY"
    broker_name: str = "shadow"

    def __post_init__(self) -> None:
        normalized_currency = self.currency.strip().upper()
        normalized_broker_name = self.broker_name.strip()

        if self.initial_cash < 0:
            raise ValueError(
                "Shadow初期資金は0以上である必要があります。"
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
                "Shadow Broker名を指定してください。"
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
        object.__setattr__(
            self,
            "ledger_path",
            Path(self.ledger_path),
        )


@dataclass(slots=True)
class _ShadowOrderState:
    """Shadow Broker内部の注文状態。"""

    order: TradeOrder
    idempotency_key: str
    broker_order_id: str
    status: OrderStatus
    submitted_at: datetime
    updated_at: datetime
    status_reason: str | None = None


class ShadowBroker:
    """ネットワーク送信せず注文計画をJSON Linesへ保存する。"""

    def __init__(
        self,
        *,
        settings: ShadowBrokerSettings | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self.settings = (
            settings
            if settings is not None
            else ShadowBrokerSettings()
        )
        self.now_provider = (
            now_provider
            if now_provider is not None
            else lambda: datetime.now(timezone.utc)
        )
        self._lock = RLock()
        self._orders: dict[str, _ShadowOrderState] = {}
        self._client_order_ids: dict[str, str] = {}
        self._load_ledger()

    @property
    def broker_name(self) -> str:
        """Broker名を返す。"""

        return self.settings.broker_name

    def submit_order(
        self,
        order: TradeOrder,
    ) -> BrokerOrderSnapshot:
        """注文計画を保存するが外部へ送信しない。"""

        return self.record_order(order).snapshot

    def record_order(
        self,
        order: TradeOrder,
    ) -> ShadowOrderRecordResult:
        """注文計画を保存し、記録・既存の判断も返す。"""

        with self._lock:
            idempotency_key = self._idempotency_key(order)
            existing_id = self._client_order_ids.get(
                order.order_id
            )

            if existing_id is not None:
                existing = self._orders[existing_id]

                if existing.idempotency_key != idempotency_key:
                    raise ShadowOrderConflictError(
                        "同じ注文IDに異なるShadow注文が"
                        "指定されました。"
                    )

                return ShadowOrderRecordResult(
                    decision=(
                        ShadowOrderRecordDecision.EXISTING
                    ),
                    order=existing.order,
                    idempotency_key=(
                        existing.idempotency_key
                    ),
                    snapshot=self._snapshot(existing),
                )

            current_time = self._current_time()
            broker_order_id = (
                f"shadow-{idempotency_key[:24]}"
            )
            state = _ShadowOrderState(
                order=order,
                idempotency_key=idempotency_key,
                broker_order_id=broker_order_id,
                status=OrderStatus.QUEUED,
                submitted_at=current_time,
                updated_at=current_time,
                status_reason=(
                    "Shadow only: no broker request was sent."
                ),
            )
            self._append_event(
                self._submitted_event(state)
            )
            self._orders[broker_order_id] = state
            self._client_order_ids[
                order.order_id
            ] = broker_order_id
            return ShadowOrderRecordResult(
                decision=(
                    ShadowOrderRecordDecision.RECORDED
                ),
                order=state.order,
                idempotency_key=state.idempotency_key,
                snapshot=self._snapshot(state),
            )

    def get_planned_order(
        self,
        broker_order_id: str,
    ) -> TradeOrder:
        """Shadow台帳に保存した元注文を返す。"""

        with self._lock:
            return self._require_order(
                broker_order_id
            ).order

    def cancel_order(
        self,
        broker_order_id: str,
    ) -> BrokerOrderSnapshot:
        """Shadow注文を取消状態にする。"""

        with self._lock:
            state = self._require_order(
                broker_order_id
            )

            if state.status is OrderStatus.CANCELLED:
                return self._snapshot(state)

            current_time = self._current_time()
            self._append_event(
                {
                    "event": "cancelled",
                    "broker_order_id": state.broker_order_id,
                    "recorded_at": current_time.isoformat(),
                }
            )
            state.status = OrderStatus.CANCELLED
            state.updated_at = current_time
            state.status_reason = (
                "Shadow order was cancelled locally."
            )
            return self._snapshot(state)

    def get_order(
        self,
        broker_order_id: str,
    ) -> BrokerOrderSnapshot:
        """Shadow注文の現在状態を返す。"""

        with self._lock:
            return self._snapshot(
                self._require_order(broker_order_id)
            )

    def list_orders(
        self,
        *,
        active_only: bool = False,
    ) -> list[BrokerOrderSnapshot]:
        """Shadow注文一覧を時系列で返す。"""

        with self._lock:
            states = sorted(
                self._orders.values(),
                key=lambda item: (
                    item.submitted_at,
                    item.broker_order_id,
                ),
            )

            if active_only:
                states = [
                    item
                    for item in states
                    if item.status.is_active
                ]

            return [
                self._snapshot(item)
                for item in states
            ]

    def list_positions(self) -> list[BrokerPosition]:
        """Shadowは約定しないためポジションを返さない。"""

        return []

    def get_account(self) -> BrokerAccountSnapshot:
        """注文で変化しない仮想口座情報を返す。"""

        current_time = self._current_time()

        return BrokerAccountSnapshot(
            currency=self.settings.currency,
            cash_balance=self.settings.initial_cash,
            buying_power=self.settings.initial_cash,
            market_value=0.0,
            equity=self.settings.initial_cash,
            updated_at=current_time,
        )

    def _load_ledger(self) -> None:
        path = self.settings.ledger_path

        if not path.exists():
            return

        try:
            lines = path.read_text(
                encoding="utf-8"
            ).splitlines()

            for line_number, line in enumerate(
                lines,
                start=1,
            ):
                if not line.strip():
                    continue

                self._apply_loaded_event(
                    json.loads(line),
                    line_number=line_number,
                )
        except (
            OSError,
            TypeError,
            ValueError,
            KeyError,
        ) as error:
            raise ShadowLedgerError(
                f"Shadow注文台帳を読み込めません。path={path}"
            ) from error

    def _apply_loaded_event(
        self,
        event: dict[str, object],
        *,
        line_number: int,
    ) -> None:
        event_type = str(event["event"])

        if event_type == "submitted":
            order_payload = event["order"]

            if not isinstance(order_payload, dict):
                raise ShadowLedgerError(
                    "Shadow注文データが不正です。"
                )

            order = TradeOrder(
                order_id=str(order_payload["order_id"]),
                signal_id=str(order_payload["signal_id"]),
                code=str(order_payload["code"]),
                side=OrderSide(str(order_payload["side"])),
                order_type=OrderType(
                    str(order_payload["order_type"])
                ),
                quantity=int(order_payload["quantity"]),
                limit_price=self._optional_float(
                    order_payload.get("limit_price")
                ),
                stop_price=self._optional_float(
                    order_payload.get("stop_price")
                ),
            )
            broker_order_id = str(
                event["broker_order_id"]
            )
            submitted_at = datetime.fromisoformat(
                str(event["recorded_at"])
            )
            state = _ShadowOrderState(
                order=order,
                idempotency_key=str(
                    event["idempotency_key"]
                ),
                broker_order_id=broker_order_id,
                status=OrderStatus.QUEUED,
                submitted_at=submitted_at,
                updated_at=submitted_at,
                status_reason=(
                    "Shadow only: no broker request was sent."
                ),
            )
            existing_id = self._client_order_ids.get(
                order.order_id
            )

            if existing_id is not None:
                raise ShadowLedgerError(
                    "Shadow注文IDが重複しています。"
                    f"line={line_number}"
                )

            self._orders[broker_order_id] = state
            self._client_order_ids[
                order.order_id
            ] = broker_order_id
            return

        if event_type == "cancelled":
            broker_order_id = str(
                event["broker_order_id"]
            )
            state = self._require_order(
                broker_order_id
            )
            updated_at = datetime.fromisoformat(
                str(event["recorded_at"])
            )
            state.status = OrderStatus.CANCELLED
            state.updated_at = updated_at
            state.status_reason = (
                "Shadow order was cancelled locally."
            )
            return

        raise ShadowLedgerError(
            "不明なShadow台帳イベントです。"
            f"line={line_number} event={event_type}"
        )

    def _append_event(
        self,
        event: dict[str, object],
    ) -> None:
        path = self.settings.ledger_path

        try:
            path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            with path.open(
                "a",
                encoding="utf-8",
                newline="\n",
            ) as stream:
                stream.write(
                    json.dumps(
                        event,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                )
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
        except OSError as error:
            raise ShadowLedgerError(
                f"Shadow注文台帳へ保存できません。path={path}"
            ) from error

    @staticmethod
    def _submitted_event(
        state: _ShadowOrderState,
    ) -> dict[str, object]:
        order = state.order

        return {
            "event": "submitted",
            "broker_order_id": state.broker_order_id,
            "idempotency_key": state.idempotency_key,
            "recorded_at": state.submitted_at.isoformat(),
            "order": {
                "order_id": order.order_id,
                "signal_id": order.signal_id,
                "code": order.code,
                "side": order.side.value,
                "order_type": order.order_type.value,
                "quantity": order.quantity,
                "limit_price": order.limit_price,
                "stop_price": order.stop_price,
            },
        }

    @staticmethod
    def _idempotency_key(
        order: TradeOrder,
    ) -> str:
        payload = {
            "order_id": order.order_id,
            "signal_id": order.signal_id,
            "code": order.code,
            "side": order.side.value,
            "order_type": order.order_type.value,
            "quantity": order.quantity,
            "limit_price": order.limit_price,
            "stop_price": order.stop_price,
        }
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _require_order(
        self,
        broker_order_id: str,
    ) -> _ShadowOrderState:
        normalized = broker_order_id.strip()

        try:
            return self._orders[normalized]
        except KeyError as error:
            raise BrokerOrderNotFoundError(
                "Shadow注文が見つかりません。"
                f"broker_order_id={normalized}"
            ) from error

    @staticmethod
    def _snapshot(
        state: _ShadowOrderState,
    ) -> BrokerOrderSnapshot:
        return BrokerOrderSnapshot(
            broker_order_id=state.broker_order_id,
            client_order_id=state.order.order_id,
            code=state.order.code,
            side=state.order.side,
            status=state.status,
            quantity=state.order.quantity,
            filled_quantity=0,
            average_fill_price=None,
            submitted_at=state.submitted_at,
            updated_at=state.updated_at,
            status_reason=state.status_reason,
        )

    def _current_time(self) -> datetime:
        current = self.now_provider()

        if current.tzinfo is None:
            raise ValueError(
                "現在日時にはタイムゾーンが必要です。"
            )

        return current

    @staticmethod
    def _optional_float(
        value: object,
    ) -> float | None:
        if value is None:
            return None

        return float(value)
