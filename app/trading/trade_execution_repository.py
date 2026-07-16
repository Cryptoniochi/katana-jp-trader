"""約定履歴をSQLiteへ追加専用で永続化する。"""

import json
import sqlite3
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from app.trading.order_models import OrderSide
from app.trading.trade_execution_models import (
    TradeExecution,
    TradeExecutionRecord,
)


class TradeExecutionRepositoryError(RuntimeError):
    """約定履歴Repositoryの基底例外。"""


class TradeExecutionNotFoundError(TradeExecutionRepositoryError):
    """指定した約定履歴が存在しないことを表す。"""


class DuplicateTradeExecutionError(TradeExecutionRepositoryError):
    """約定IDが重複したことを表す。"""


class TradeExecutionRepository:
    """約定履歴を追加専用で管理する。"""

    def __init__(
        self,
        database_path: Path,
        *,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self.database_path = database_path
        self.now_provider = (
            now_provider
            if now_provider is not None
            else lambda: datetime.now(timezone.utc)
        )

    def save(
        self,
        execution: TradeExecution,
    ) -> TradeExecutionRecord:
        current_time = self._current_time()
        normalized = TradeExecution(
            execution_id=execution.execution_id,
            signal_id=execution.signal_id,
            order_id=execution.order_id,
            broker_order_id=execution.broker_order_id,
            code=execution.code,
            side=execution.side,
            quantity=execution.quantity,
            execution_price=execution.execution_price,
            executed_at=execution.executed_at.astimezone(timezone.utc),
            broker_name=execution.broker_name,
            commission=execution.commission,
            slippage=execution.slippage,
            metadata=execution.metadata,
        )

        try:
            metadata_json = json.dumps(
                normalized.metadata,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        except (TypeError, ValueError) as error:
            raise ValueError(
                "メタデータをJSONへ変換できません。"
            ) from error

        try:
            with self._connect() as connection:
                cursor = connection.execute(
                    """
                    INSERT INTO trade_executions (
                        execution_id,
                        signal_id,
                        order_id,
                        broker_order_id,
                        code,
                        side,
                        quantity,
                        execution_price,
                        executed_at,
                        broker_name,
                        commission,
                        slippage,
                        metadata_json,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        normalized.execution_id,
                        normalized.signal_id,
                        normalized.order_id,
                        normalized.broker_order_id,
                        normalized.code,
                        normalized.side.value,
                        normalized.quantity,
                        normalized.execution_price,
                        normalized.executed_at.isoformat(),
                        normalized.broker_name,
                        normalized.commission,
                        normalized.slippage,
                        metadata_json,
                        current_time.isoformat(),
                        current_time.isoformat(),
                    ),
                )
                connection.commit()
                record_id = int(cursor.lastrowid)
        except sqlite3.IntegrityError as error:
            raise DuplicateTradeExecutionError(
                "約定IDが既に使用されているか、"
                "関連するシグナル・注文が存在しません。 "
                f"execution_id={normalized.execution_id}"
            ) from error
        except sqlite3.Error as error:
            raise TradeExecutionRepositoryError(
                "約定履歴を保存できませんでした。 "
                f"execution_id={normalized.execution_id}"
            ) from error

        return TradeExecutionRecord(
            id=record_id,
            execution=normalized,
            created_at=current_time,
            updated_at=current_time,
        )

    def get(
        self,
        execution_id: str,
    ) -> TradeExecutionRecord:
        normalized = self._normalize_required(
            execution_id,
            "約定ID",
        )

        try:
            with self._connect() as connection:
                row = connection.execute(
                    self._select_sql()
                    + """
                    WHERE execution_id = ?
                    """,
                    (normalized,),
                ).fetchone()
        except sqlite3.Error as error:
            raise TradeExecutionRepositoryError(
                "約定履歴を読み込めませんでした。 "
                f"execution_id={normalized}"
            ) from error

        if row is None:
            raise TradeExecutionNotFoundError(
                "指定された約定履歴が存在しません。 "
                f"execution_id={normalized}"
            )

        return self._row_to_record(row)

    def latest(
        self,
        *,
        code: str | None = None,
    ) -> TradeExecutionRecord | None:
        records = self.list_recent(limit=1, code=code)
        return records[0] if records else None

    def list_recent(
        self,
        *,
        limit: int = 100,
        code: str | None = None,
        side: OrderSide | None = None,
        order_id: str | None = None,
        signal_id: str | None = None,
    ) -> list[TradeExecutionRecord]:
        if limit <= 0:
            raise ValueError(
                "取得件数は0より大きい必要があります。"
            )

        conditions: list[str] = []
        parameters: list[object] = []

        if code is not None:
            conditions.append("code = ?")
            parameters.append(self._normalize_code(code))
        if side is not None:
            conditions.append("side = ?")
            parameters.append(side.value)
        if order_id is not None:
            conditions.append("order_id = ?")
            parameters.append(
                self._normalize_required(order_id, "注文ID")
            )
        if signal_id is not None:
            conditions.append("signal_id = ?")
            parameters.append(
                self._normalize_required(signal_id, "シグナルID")
            )

        where_clause = (
            "WHERE " + " AND ".join(conditions)
            if conditions
            else ""
        )
        parameters.append(limit)

        try:
            with self._connect() as connection:
                rows = connection.execute(
                    self._select_sql()
                    + f"""
                    {where_clause}
                    ORDER BY executed_at DESC, id DESC
                    LIMIT ?
                    """,
                    parameters,
                ).fetchall()
        except sqlite3.Error as error:
            raise TradeExecutionRepositoryError(
                "約定履歴一覧を読み込めませんでした。"
            ) from error

        return [self._row_to_record(row) for row in rows]

    def find_by_order(
        self,
        order_id: str,
    ) -> list[TradeExecutionRecord]:
        return self.list_recent(order_id=order_id)

    def find_by_signal(
        self,
        signal_id: str,
    ) -> list[TradeExecutionRecord]:
        return self.list_recent(signal_id=signal_id)

    def count(
        self,
        *,
        code: str | None = None,
        side: OrderSide | None = None,
        order_id: str | None = None,
        signal_id: str | None = None,
    ) -> int:
        conditions: list[str] = []
        parameters: list[object] = []

        if code is not None:
            conditions.append("code = ?")
            parameters.append(self._normalize_code(code))
        if side is not None:
            conditions.append("side = ?")
            parameters.append(side.value)
        if order_id is not None:
            conditions.append("order_id = ?")
            parameters.append(
                self._normalize_required(order_id, "注文ID")
            )
        if signal_id is not None:
            conditions.append("signal_id = ?")
            parameters.append(
                self._normalize_required(signal_id, "シグナルID")
            )

        where_clause = (
            "WHERE " + " AND ".join(conditions)
            if conditions
            else ""
        )

        try:
            with self._connect() as connection:
                row = connection.execute(
                    f"""
                    SELECT COUNT(*)
                    FROM trade_executions
                    {where_clause}
                    """,
                    parameters,
                ).fetchone()
        except sqlite3.Error as error:
            raise TradeExecutionRepositoryError(
                "約定履歴件数を取得できませんでした。"
            ) from error

        return int(row[0]) if row is not None else 0

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _current_time(self) -> datetime:
        current_time = self.now_provider()

        if current_time.tzinfo is None:
            raise ValueError(
                "現在日時にはタイムゾーンが必要です。"
            )

        return current_time.astimezone(timezone.utc)

    @staticmethod
    def _normalize_required(
        value: str,
        name: str,
    ) -> str:
        normalized = value.strip()

        if not normalized:
            raise ValueError(f"{name}を指定してください。")

        return normalized

    @classmethod
    def _normalize_code(cls, code: str) -> str:
        normalized = cls._normalize_required(code, "銘柄コード")

        if not normalized.isdigit():
            raise ValueError("銘柄コードは数字で指定してください。")

        if len(normalized) not in {4, 5}:
            raise ValueError(
                "銘柄コードは4桁または5桁で指定してください。"
            )

        return normalized

    @staticmethod
    def _select_sql() -> str:
        return """
            SELECT
                id,
                execution_id,
                signal_id,
                order_id,
                broker_order_id,
                code,
                side,
                quantity,
                execution_price,
                executed_at,
                broker_name,
                commission,
                slippage,
                metadata_json,
                created_at,
                updated_at
            FROM trade_executions
        """

    @classmethod
    def _row_to_record(
        cls,
        row: tuple[object, ...],
    ) -> TradeExecutionRecord:
        try:
            metadata = json.loads(str(row[13]))
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            raise TradeExecutionRepositoryError(
                "保存済みメタデータを読み込めませんでした。"
            ) from error

        execution = TradeExecution(
            execution_id=str(row[1]),
            signal_id=str(row[2]),
            order_id=str(row[3]),
            broker_order_id=str(row[4]),
            code=str(row[5]),
            side=OrderSide(str(row[6])),
            quantity=int(row[7]),
            execution_price=float(row[8]),
            executed_at=cls._parse_datetime(str(row[9])),
            broker_name=str(row[10]),
            commission=float(row[11]),
            slippage=float(row[12]),
            metadata=metadata,
        )

        return TradeExecutionRecord(
            id=int(row[0]),
            execution=execution,
            created_at=cls._parse_datetime(str(row[14])),
            updated_at=cls._parse_datetime(str(row[15])),
        )

    @staticmethod
    def _parse_datetime(value: str) -> datetime:
        parsed = datetime.fromisoformat(value)

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)

        return parsed.astimezone(timezone.utc)
