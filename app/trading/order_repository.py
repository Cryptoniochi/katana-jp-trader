"""売買注文とライフサイクルをSQLiteで管理する。"""

import sqlite3
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from app.trading.order_models import (
    OrderSide,
    OrderStatus,
    OrderType,
    TradeOrder,
    TradeOrderRecord,
)


class OrderRepositoryError(RuntimeError):
    """注文Repositoryの基底例外。"""


class OrderNotFoundError(OrderRepositoryError):
    """指定された注文が存在しないことを表す。"""


class DuplicateOrderError(OrderRepositoryError):
    """注文IDまたはシグナルIDが重複したことを表す。"""


class OrderStateTransitionError(OrderRepositoryError):
    """許可されない注文状態遷移を表す。"""


class OrderRepository:
    """注文の作成・取得・状態遷移を管理する。"""

    ALLOWED_TRANSITIONS = {
        OrderStatus.NEW: {
            OrderStatus.QUEUED,
            OrderStatus.CANCELLED,
            OrderStatus.REJECTED,
            OrderStatus.FAILED,
        },
        OrderStatus.QUEUED: {
            OrderStatus.SENT,
            OrderStatus.CANCELLED,
            OrderStatus.REJECTED,
            OrderStatus.FAILED,
        },
        OrderStatus.SENT: {
            OrderStatus.PARTIALLY_FILLED,
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.REJECTED,
            OrderStatus.FAILED,
        },
        OrderStatus.PARTIALLY_FILLED: {
            OrderStatus.PARTIALLY_FILLED,
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.FAILED,
        },
    }

    def __init__(
        self,
        database_path: Path,
        *,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        """DBパスと現在日時取得処理を設定する。"""

        self.database_path = database_path
        self.now_provider = (
            now_provider
            if now_provider is not None
            else lambda: datetime.now(timezone.utc)
        )

    def create(
        self,
        order: TradeOrder,
    ) -> TradeOrderRecord:
        """注文をNEW状態で保存する。"""

        current_time = self._current_time()

        try:
            with self._connect() as connection:
                cursor = connection.execute(
                    """
                    INSERT INTO trade_orders (
                        order_id,
                        signal_id,
                        code,
                        side,
                        order_type,
                        quantity,
                        limit_price,
                        stop_price,
                        status,
                        filled_quantity,
                        average_fill_price,
                        broker_order_id,
                        status_reason,
                        error_message,
                        created_at,
                        updated_at,
                        submitted_at,
                        completed_at
                    )
                    VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, 0, NULL, NULL, NULL, NULL,
                        ?, ?, NULL, NULL
                    )
                    """,
                    (
                        order.order_id,
                        order.signal_id,
                        order.code,
                        order.side.value,
                        order.order_type.value,
                        order.quantity,
                        order.limit_price,
                        order.stop_price,
                        OrderStatus.NEW.value,
                        current_time.isoformat(),
                        current_time.isoformat(),
                    ),
                )

                connection.commit()
                record_id = int(cursor.lastrowid)

        except sqlite3.IntegrityError as error:
            raise DuplicateOrderError(
                "注文IDまたはシグナルIDが"
                "既に使用されています。 "
                f"order_id={order.order_id} "
                f"signal_id={order.signal_id}"
            ) from error

        except sqlite3.Error as error:
            raise OrderRepositoryError(
                "注文を保存できませんでした。 "
                f"order_id={order.order_id}"
            ) from error

        return TradeOrderRecord(
            id=record_id,
            order=order,
            status=OrderStatus.NEW,
            filled_quantity=0,
            average_fill_price=None,
            broker_order_id=None,
            status_reason=None,
            error_message=None,
            created_at=current_time,
            updated_at=current_time,
            submitted_at=None,
            completed_at=None,
        )

    def get(
        self,
        order_id: str,
    ) -> TradeOrderRecord:
        """注文IDに一致する注文を返す。"""

        normalized_order_id = self._normalize_required(
            order_id,
            "注文ID",
        )

        try:
            with self._connect() as connection:
                row = connection.execute(
                    self._select_sql()
                    + """
                    WHERE order_id = ?
                    """,
                    (
                        normalized_order_id,
                    ),
                ).fetchone()

        except sqlite3.Error as error:
            raise OrderRepositoryError(
                "注文を読み込めませんでした。 "
                f"order_id={normalized_order_id}"
            ) from error

        if row is None:
            raise OrderNotFoundError(
                "指定された注文が存在しません。 "
                f"order_id={normalized_order_id}"
            )

        return self._row_to_record(
            row,
        )

    def get_by_signal_id(
        self,
        signal_id: str,
    ) -> TradeOrderRecord | None:
        """元シグナルIDに対応する注文を返す。"""

        normalized_signal_id = self._normalize_required(
            signal_id,
            "シグナルID",
        )

        try:
            with self._connect() as connection:
                row = connection.execute(
                    self._select_sql()
                    + """
                    WHERE signal_id = ?
                    """,
                    (
                        normalized_signal_id,
                    ),
                ).fetchone()

        except sqlite3.Error as error:
            raise OrderRepositoryError(
                "シグナルに対応する注文を"
                "読み込めませんでした。 "
                f"signal_id={normalized_signal_id}"
            ) from error

        if row is None:
            return None

        return self._row_to_record(
            row,
        )

    def list_recent(
        self,
        *,
        limit: int = 100,
        code: str | None = None,
        status: OrderStatus | None = None,
        side: OrderSide | None = None,
    ) -> list[TradeOrderRecord]:
        """条件に一致する注文を新しい順に返す。"""

        if limit <= 0:
            raise ValueError(
                "取得件数は0より大きい必要があります。"
            )

        conditions: list[str] = []
        parameters: list[object] = []

        if code is not None:
            conditions.append(
                "code = ?"
            )
            parameters.append(
                self._normalize_code(code)
            )

        if status is not None:
            conditions.append(
                "status = ?"
            )
            parameters.append(
                status.value
            )

        if side is not None:
            conditions.append(
                "side = ?"
            )
            parameters.append(
                side.value
            )

        where_clause = ""

        if conditions:
            where_clause = (
                "WHERE "
                + " AND ".join(conditions)
            )

        parameters.append(limit)

        try:
            with self._connect() as connection:
                rows = connection.execute(
                    self._select_sql()
                    + f"""
                    {where_clause}
                    ORDER BY created_at DESC, id DESC
                    LIMIT ?
                    """,
                    parameters,
                ).fetchall()

        except sqlite3.Error as error:
            raise OrderRepositoryError(
                "注文一覧を読み込めませんでした。"
            ) from error

        return [
            self._row_to_record(row)
            for row in rows
        ]

    def count(
        self,
        *,
        code: str | None = None,
        status: OrderStatus | None = None,
        side: OrderSide | None = None,
    ) -> int:
        """条件に一致する注文件数を返す。"""

        conditions: list[str] = []
        parameters: list[object] = []

        if code is not None:
            conditions.append("code = ?")
            parameters.append(
                self._normalize_code(code)
            )

        if status is not None:
            conditions.append("status = ?")
            parameters.append(status.value)

        if side is not None:
            conditions.append("side = ?")
            parameters.append(side.value)

        where_clause = ""

        if conditions:
            where_clause = (
                "WHERE "
                + " AND ".join(conditions)
            )

        try:
            with self._connect() as connection:
                row = connection.execute(
                    f"""
                    SELECT COUNT(*)
                    FROM trade_orders
                    {where_clause}
                    """,
                    parameters,
                ).fetchone()

        except sqlite3.Error as error:
            raise OrderRepositoryError(
                "注文件数を取得できませんでした。"
            ) from error

        if row is None:
            return 0

        return int(row[0])

    def transition(
        self,
        order_id: str,
        *,
        target_status: OrderStatus,
        filled_quantity: int | None = None,
        average_fill_price: float | None = None,
        broker_order_id: str | None = None,
        status_reason: str | None = None,
        error_message: str | None = None,
    ) -> TradeOrderRecord:
        """注文を許可された次状態へ更新する。"""

        current = self.get(order_id)

        allowed_statuses = self.ALLOWED_TRANSITIONS.get(
            current.status,
            set(),
        )

        if target_status not in allowed_statuses:
            raise OrderStateTransitionError(
                "許可されていない注文状態遷移です。 "
                f"order_id={current.order_id} "
                f"current={current.status.value} "
                f"target={target_status.value}"
            )

        resolved_filled_quantity = (
            current.filled_quantity
            if filled_quantity is None
            else filled_quantity
        )

        resolved_average_fill_price = (
            current.average_fill_price
            if average_fill_price is None
            else average_fill_price
        )

        resolved_broker_order_id = (
            current.broker_order_id
            if broker_order_id is None
            else self._normalize_optional(
                broker_order_id
            )
        )

        resolved_status_reason = (
            current.status_reason
            if status_reason is None
            else self._normalize_optional(
                status_reason
            )
        )

        resolved_error_message = (
            current.error_message
            if error_message is None
            else self._normalize_optional(
                error_message
            )
        )

        current_time = self._current_time()

        if current_time < current.updated_at:
            raise ValueError(
                "状態遷移日時は直前の更新日時以後で"
                "ある必要があります。"
            )

        submitted_at = current.submitted_at

        if (
            target_status is OrderStatus.SENT
            and submitted_at is None
        ):
            submitted_at = current_time

        completed_at = (
            current_time
            if target_status.is_terminal
            else None
        )

        candidate = TradeOrderRecord(
            id=current.id,
            order=current.order,
            status=target_status,
            filled_quantity=resolved_filled_quantity,
            average_fill_price=resolved_average_fill_price,
            broker_order_id=resolved_broker_order_id,
            status_reason=resolved_status_reason,
            error_message=resolved_error_message,
            created_at=current.created_at,
            updated_at=current_time,
            submitted_at=submitted_at,
            completed_at=completed_at,
        )

        try:
            with self._connect() as connection:
                cursor = connection.execute(
                    """
                    UPDATE trade_orders
                    SET
                        status = ?,
                        filled_quantity = ?,
                        average_fill_price = ?,
                        broker_order_id = ?,
                        status_reason = ?,
                        error_message = ?,
                        updated_at = ?,
                        submitted_at = ?,
                        completed_at = ?
                    WHERE order_id = ?
                      AND status = ?
                    """,
                    (
                        candidate.status.value,
                        candidate.filled_quantity,
                        candidate.average_fill_price,
                        candidate.broker_order_id,
                        candidate.status_reason,
                        candidate.error_message,
                        candidate.updated_at.isoformat(),
                        (
                            candidate.submitted_at.isoformat()
                            if candidate.submitted_at is not None
                            else None
                        ),
                        (
                            candidate.completed_at.isoformat()
                            if candidate.completed_at is not None
                            else None
                        ),
                        candidate.order_id,
                        current.status.value,
                    ),
                )

                connection.commit()

                if cursor.rowcount != 1:
                    raise OrderStateTransitionError(
                        "注文状態を更新できませんでした。 "
                        f"order_id={candidate.order_id}"
                    )

        except OrderStateTransitionError:
            raise

        except sqlite3.Error as error:
            raise OrderRepositoryError(
                "注文状態を更新できませんでした。 "
                f"order_id={candidate.order_id}"
            ) from error

        return self.get(
            candidate.order_id
        )

    def _connect(
        self,
    ) -> sqlite3.Connection:
        """外部キー制約を有効にした接続を返す。"""

        connection = sqlite3.connect(
            self.database_path
        )
        connection.execute(
            "PRAGMA foreign_keys = ON"
        )

        return connection

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
            timezone.utc
        )

    @staticmethod
    def _normalize_required(
        value: str,
        name: str,
    ) -> str:
        """必須文字列を正規化する。"""

        normalized = value.strip()

        if not normalized:
            raise ValueError(
                f"{name}を指定してください。"
            )

        return normalized

    @classmethod
    def _normalize_code(
        cls,
        code: str,
    ) -> str:
        """銘柄コードを検証する。"""

        normalized = cls._normalize_required(
            code,
            "銘柄コード",
        )

        if not normalized.isdigit():
            raise ValueError(
                "銘柄コードは数字で指定してください。"
            )

        if len(normalized) not in {
            4,
            5,
        }:
            raise ValueError(
                "銘柄コードは4桁または5桁で"
                "指定してください。"
            )

        return normalized

    @staticmethod
    def _normalize_optional(
        value: str,
    ) -> str | None:
        """任意文字列を正規化する。"""

        normalized = value.strip()

        if not normalized:
            return None

        return normalized

    @staticmethod
    def _select_sql() -> str:
        """注文取得用SELECT文を返す。"""

        return """
            SELECT
                id,
                order_id,
                signal_id,
                code,
                side,
                order_type,
                quantity,
                limit_price,
                stop_price,
                status,
                filled_quantity,
                average_fill_price,
                broker_order_id,
                status_reason,
                error_message,
                created_at,
                updated_at,
                submitted_at,
                completed_at
            FROM trade_orders
        """

    @classmethod
    def _row_to_record(
        cls,
        row: tuple[object, ...],
    ) -> TradeOrderRecord:
        """SQLiteの1行を注文レコードへ変換する。"""

        order = TradeOrder(
            order_id=str(row[1]),
            signal_id=str(row[2]),
            code=str(row[3]),
            side=OrderSide(str(row[4])),
            order_type=OrderType(str(row[5])),
            quantity=int(row[6]),
            limit_price=(
                float(row[7])
                if row[7] is not None
                else None
            ),
            stop_price=(
                float(row[8])
                if row[8] is not None
                else None
            ),
        )

        return TradeOrderRecord(
            id=int(row[0]),
            order=order,
            status=OrderStatus(str(row[9])),
            filled_quantity=int(row[10]),
            average_fill_price=(
                float(row[11])
                if row[11] is not None
                else None
            ),
            broker_order_id=(
                str(row[12])
                if row[12] is not None
                else None
            ),
            status_reason=(
                str(row[13])
                if row[13] is not None
                else None
            ),
            error_message=(
                str(row[14])
                if row[14] is not None
                else None
            ),
            created_at=datetime.fromisoformat(
                str(row[15])
            ),
            updated_at=datetime.fromisoformat(
                str(row[16])
            ),
            submitted_at=(
                datetime.fromisoformat(str(row[17]))
                if row[17] is not None
                else None
            ),
            completed_at=(
                datetime.fromisoformat(str(row[18]))
                if row[18] is not None
                else None
            ),
        )