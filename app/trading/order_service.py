"""保存済み売買シグナルから注文を安全かつ冪等に作成する。"""

import hashlib
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from app.trading.order_models import (
    OrderSide,
    OrderType,
    TradeOrder,
    TradeOrderRecord,
)
from app.trading.order_repository import (
    DuplicateOrderError,
)
from app.trading.signal_models import (
    SignalAction,
    SignalStatus,
    TradeSignalRecord,
)
from app.trading.signal_repository import (
    SignalNotFoundError,
)


DEFAULT_ORDER_ID_PREFIX = "order"


class SignalOrderCreationDecision(StrEnum):
    """シグナルから注文を作成した結果。"""

    CREATED = "created"
    EXISTING = "existing"
    FAILED = "failed"


class SignalReaderWriter(Protocol):
    """注文作成時に使用するSignalRepositoryのインターフェース。"""

    def get(
        self,
        signal_id: str,
    ) -> TradeSignalRecord:
        """シグナルIDに一致するシグナルを返す。"""

    def mark_processed(
        self,
        signal_id: str,
        *,
        process_note: str | None = None,
    ) -> TradeSignalRecord:
        """シグナルを処理済みに更新する。"""


class OrderReaderWriter(Protocol):
    """注文作成時に使用するOrderRepositoryのインターフェース。"""

    def create(
        self,
        order: TradeOrder,
    ) -> TradeOrderRecord:
        """注文をNEW状態で保存する。"""

    def get_by_signal_id(
        self,
        signal_id: str,
    ) -> TradeOrderRecord | None:
        """シグナルIDに対応する注文を返す。"""


class SignalOrderServiceError(RuntimeError):
    """シグナル注文作成サービスの基底例外。"""


class SignalNotOrderableError(SignalOrderServiceError):
    """注文へ変換できないシグナル状態を表す。"""


class SignalOrderConsistencyError(SignalOrderServiceError):
    """シグナルと注文の保存状態に不整合があることを表す。"""


class SignalOrderConflictError(SignalOrderServiceError):
    """既存注文と要求された注文内容が一致しないことを表す。"""


@dataclass(frozen=True, slots=True)
class SignalOrderServiceSettings:
    """シグナルから注文を作成する共通設定。"""

    order_id_prefix: str = DEFAULT_ORDER_ID_PREFIX
    processed_note: str = "trade order created"

    def __post_init__(self) -> None:
        """不正な共通設定を拒否する。"""

        normalized_prefix = self.order_id_prefix.strip()
        normalized_note = self.processed_note.strip()

        if not normalized_prefix:
            raise ValueError(
                "注文IDプレフィックスを指定してください。"
            )

        if not normalized_note:
            raise ValueError(
                "シグナル処理メモを指定してください。"
            )

        object.__setattr__(
            self,
            "order_id_prefix",
            normalized_prefix,
        )
        object.__setattr__(
            self,
            "processed_note",
            normalized_note,
        )


@dataclass(frozen=True, slots=True)
class SignalOrderCreationResult:
    """1件のシグナルから注文を作成した結果。"""

    decision: SignalOrderCreationDecision
    signal_record: TradeSignalRecord | None
    order_record: TradeOrderRecord | None
    message: str | None

    @property
    def was_created(self) -> bool:
        """新しい注文を作成したか返す。"""

        return (
            self.decision
            is SignalOrderCreationDecision.CREATED
        )

    @property
    def was_existing(self) -> bool:
        """既存注文を再利用したか返す。"""

        return (
            self.decision
            is SignalOrderCreationDecision.EXISTING
        )

    @property
    def is_failed(self) -> bool:
        """注文作成処理に失敗したか返す。"""

        return (
            self.decision
            is SignalOrderCreationDecision.FAILED
        )


class SignalOrderService:
    """保存済みシグナルをTradeOrderへ変換して永続化する。"""

    def __init__(
        self,
        *,
        signal_repository: SignalReaderWriter,
        order_repository: OrderReaderWriter,
        settings: SignalOrderServiceSettings | None = None,
    ) -> None:
        """Signal・OrderのRepositoryと共通設定を受け取る。"""

        self.signal_repository = signal_repository
        self.order_repository = order_repository
        self.settings = (
            settings
            if settings is not None
            else SignalOrderServiceSettings()
        )

    def create_from_signal(
        self,
        signal_id: str,
        *,
        order_type: OrderType = OrderType.MARKET,
        limit_price: float | None = None,
        stop_price: float | None = None,
        continue_on_error: bool = False,
    ) -> SignalOrderCreationResult:
        """シグナルから注文を作成し、シグナルを処理済みにする。

        同じシグナルに対応する注文が既にある場合は、
        注文内容を検証して既存注文を返す。

        注文保存後にシグナル更新だけが失敗した場合も、
        再実行時に既存注文を検出して処理済み更新を再試行する。
        """

        try:
            signal_record = self.signal_repository.get(
                signal_id,
            )

            expected_order = self._create_order(
                signal_record=signal_record,
                order_type=order_type,
                limit_price=limit_price,
                stop_price=stop_price,
            )

            existing_order = (
                self.order_repository.get_by_signal_id(
                    signal_record.signal_id,
                )
            )

            if existing_order is not None:
                self._validate_existing_order(
                    existing=existing_order,
                    expected=expected_order,
                )

                finalized_signal = (
                    self._finalize_signal_for_existing_order(
                        signal_record=signal_record,
                        order_record=existing_order,
                    )
                )

                return SignalOrderCreationResult(
                    decision=(
                        SignalOrderCreationDecision.EXISTING
                    ),
                    signal_record=finalized_signal,
                    order_record=existing_order,
                    message=(
                        "シグナルに対応する既存注文を"
                        "再利用しました。"
                    ),
                )

            if signal_record.status is SignalStatus.CANCELLED:
                raise SignalNotOrderableError(
                    "取消済みシグナルから注文は作成できません。 "
                    f"signal_id={signal_record.signal_id}"
                )

            if signal_record.status is SignalStatus.PROCESSED:
                raise SignalOrderConsistencyError(
                    "処理済みシグナルに対応する注文が"
                    "存在しません。 "
                    f"signal_id={signal_record.signal_id}"
                )

            if signal_record.status is not SignalStatus.PENDING:
                raise SignalNotOrderableError(
                    "未処理ではないシグナルから"
                    "注文は作成できません。 "
                    f"signal_id={signal_record.signal_id} "
                    f"status={signal_record.status.value}"
                )

            try:
                order_record = self.order_repository.create(
                    expected_order,
                )

            except DuplicateOrderError:
                concurrent_order = (
                    self.order_repository.get_by_signal_id(
                        signal_record.signal_id,
                    )
                )

                if concurrent_order is None:
                    raise SignalOrderConsistencyError(
                        "注文重複が検出されましたが、"
                        "対応する既存注文を取得できません。 "
                        f"signal_id={signal_record.signal_id}"
                    )

                self._validate_existing_order(
                    existing=concurrent_order,
                    expected=expected_order,
                )

                finalized_signal = (
                    self._finalize_signal_for_existing_order(
                        signal_record=signal_record,
                        order_record=concurrent_order,
                    )
                )

                return SignalOrderCreationResult(
                    decision=(
                        SignalOrderCreationDecision.EXISTING
                    ),
                    signal_record=finalized_signal,
                    order_record=concurrent_order,
                    message=(
                        "同時実行で先に作成された注文を"
                        "再利用しました。"
                    ),
                )

            finalized_signal = (
                self.signal_repository.mark_processed(
                    signal_record.signal_id,
                    process_note=(
                        self.settings.processed_note
                    ),
                )
            )

            return SignalOrderCreationResult(
                decision=(
                    SignalOrderCreationDecision.CREATED
                ),
                signal_record=finalized_signal,
                order_record=order_record,
                message=None,
            )

        except Exception as error:
            if not continue_on_error:
                raise

            return SignalOrderCreationResult(
                decision=(
                    SignalOrderCreationDecision.FAILED
                ),
                signal_record=None,
                order_record=None,
                message=str(error),
            )

    def _finalize_signal_for_existing_order(
        self,
        *,
        signal_record: TradeSignalRecord,
        order_record: TradeOrderRecord,
    ) -> TradeSignalRecord:
        """既存注文に対応するシグナル状態を整合させる。"""

        if signal_record.status is SignalStatus.CANCELLED:
            raise SignalOrderConsistencyError(
                "取消済みシグナルに対応する注文が"
                "存在します。 "
                f"signal_id={signal_record.signal_id} "
                f"order_id={order_record.order_id}"
            )

        if signal_record.status is SignalStatus.PROCESSED:
            return signal_record

        if signal_record.status is not SignalStatus.PENDING:
            raise SignalOrderConsistencyError(
                "既存注文に対応するシグナル状態が"
                "不正です。 "
                f"signal_id={signal_record.signal_id} "
                f"status={signal_record.status.value}"
            )

        return self.signal_repository.mark_processed(
            signal_record.signal_id,
            process_note=self.settings.processed_note,
        )

    def _create_order(
        self,
        *,
        signal_record: TradeSignalRecord,
        order_type: OrderType,
        limit_price: float | None,
        stop_price: float | None,
    ) -> TradeOrder:
        """シグナル内容から注文モデルを作成する。"""

        signal = signal_record.signal

        return TradeOrder(
            order_id=self._create_order_id(
                signal.signal_id,
            ),
            signal_id=signal.signal_id,
            code=signal.code,
            side=self._resolve_order_side(
                signal.action,
            ),
            order_type=order_type,
            quantity=signal.quantity,
            limit_price=limit_price,
            stop_price=stop_price,
        )

    def _create_order_id(
        self,
        signal_id: str,
    ) -> str:
        """シグナルIDから再現可能な注文IDを生成する。"""

        digest = hashlib.sha256(
            signal_id.encode(
                "utf-8",
            )
        ).hexdigest()[:24]

        return (
            f"{self.settings.order_id_prefix}"
            f"-{digest}"
        )

    @staticmethod
    def _resolve_order_side(
        action: SignalAction,
    ) -> OrderSide:
        """シグナル指示を注文の売買方向へ変換する。"""

        if action is SignalAction.BUY:
            return OrderSide.BUY

        if action in {
            SignalAction.SELL,
            SignalAction.EXIT,
        }:
            return OrderSide.SELL

        raise ValueError(
            "未対応のシグナル指示です。 "
            f"action={action}"
        )

    @staticmethod
    def _validate_existing_order(
        *,
        existing: TradeOrderRecord,
        expected: TradeOrder,
    ) -> None:
        """既存注文が今回要求された注文内容と一致するか検証する。"""

        if existing.order == expected:
            return

        raise SignalOrderConflictError(
            "シグナルに対応する既存注文の内容が"
            "今回の要求と一致しません。 "
            f"signal_id={expected.signal_id} "
            f"existing_order_id={existing.order_id} "
            f"expected_order_id={expected.order_id}"
        )