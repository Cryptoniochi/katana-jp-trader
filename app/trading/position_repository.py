"""現在ポジションをSQLiteで管理する。"""

import sqlite3
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from app.trading.broker_adapter import BrokerPositionSide
from app.trading.position_models import (
    TradingPosition,
    TradingPositionRecord,
)


class PositionRepositoryError(RuntimeError):
    """ポジションRepositoryの基底例外。"""


class PositionNotFoundError(PositionRepositoryError):
    """指定されたポジションが存在しないことを表す。"""


class DuplicatePositionError(PositionRepositoryError):
    """ポジションIDまたは銘柄・方向が重複したことを表す。"""


class PositionRepository:
    """現在保有ポジションを永続化する。"""

    def __init__(
        self,
        database_path: Path,
        *,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        """DBパスと時計を設定する。"""

        self.database_path = database_path
        self.now_provider = (
            now_provider
            if now_provider is not None
            else lambda: datetime.now(timezone.utc)
        )

    def create(
        self,
        position: TradingPosition,
    ) -> TradingPositionRecord:
        """新しい現在ポジションを保存する。"""

        current_time = self._current_time()
        normalized_opened_at = position.opened_at.astimezone(
            timezone.utc
        )
        normalized_position = TradingPosition(
            position_id=position.position_id,
            code=position.code,
            side=position.side,
            quantity=position.quantity,
            average_cost=position.average_cost,
            realized_profit_loss=position.realized_profit_loss,
            opened_at=normalized_opened_at,
        )

        try:
            with self._connect() as connection:
                cursor = connection.execute(
                    """
                    INSERT INTO positions (
                        position_id,
                        code,
                        side,
                        quantity,
                        average_cost,
                        realized_profit_loss,
                        opened_at,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        normalized_position.position_id,
                        normalized_position.code,
                        normalized_position.side.value,
                        normalized_position.quantity,
                        normalized_position.average_cost,
                        normalized_position.realized_profit_loss,
                        normalized_position.opened_at.isoformat(),
                        current_time.isoformat(),
                        current_time.isoformat(),
                    ),
                )
                connection.commit()
                record_id = int(cursor.lastrowid)

        except sqlite3.IntegrityError as error:
            raise DuplicatePositionError(
                "ポジションIDまたは銘柄・方向が"
                "既に使用されています。 "
                f"position_id={normalized_position.position_id} "
                f"code={normalized_position.code} "
                f"side={normalized_position.side.value}"
            ) from error
        except sqlite3.Error as error:
            raise PositionRepositoryError(
                "ポジションを保存できませんでした。 "
                f"position_id={normalized_position.position_id}"
            ) from error

        return TradingPositionRecord(
            id=record_id,
            position=normalized_position,
            created_at=current_time,
            updated_at=current_time,
        )

    def get(
        self,
        position_id: str,
    ) -> TradingPositionRecord:
        """ポジションIDに一致する現在ポジションを返す。"""

        normalized_position_id = self._normalize_required(
            position_id,
            "ポジションID",
        )

        try:
            with self._connect() as connection:
                row = connection.execute(
                    self._select_sql()
                    + """
                    WHERE position_id = ?
                    """,
                    (normalized_position_id,),
                ).fetchone()
        except sqlite3.Error as error:
            raise PositionRepositoryError(
                "ポジションを読み込めませんでした。 "
                f"position_id={normalized_position_id}"
            ) from error

        if row is None:
            raise PositionNotFoundError(
                "指定されたポジションが存在しません。 "
                f"position_id={normalized_position_id}"
            )

        return self._row_to_record(row)

    def get_by_identity(
        self,
        *,
        code: str,
        side: BrokerPositionSide,
    ) -> TradingPositionRecord | None:
        """銘柄コード・方向に一致する現在ポジションを返す。"""

        normalized_code = self._normalize_code(code)

        try:
            with self._connect() as connection:
                row = connection.execute(
                    self._select_sql()
                    + """
                    WHERE code = ?
                      AND side = ?
                    """,
                    (
                        normalized_code,
                        side.value,
                    ),
                ).fetchone()
        except sqlite3.Error as error:
            raise PositionRepositoryError(
                "銘柄・方向に対応するポジションを"
                "読み込めませんでした。 "
                f"code={normalized_code} "
                f"side={side.value}"
            ) from error

        if row is None:
            return None

        return self._row_to_record(row)

    def update(
        self,
        position: TradingPosition,
    ) -> TradingPositionRecord:
        """既存ポジションの数量・平均取得価格等を更新する。"""

        current = self.get(position.position_id)

        if (
            current.code != position.code.strip()
            or current.side is not position.side
        ):
            raise ValueError(
                "更新時に銘柄コードまたは"
                "ポジション方向を変更できません。"
            )

        current_time = self._current_time()

        if current_time < current.updated_at:
            raise ValueError(
                "更新日時は前回更新日時以後である必要があります。"
            )

        normalized_position = TradingPosition(
            position_id=position.position_id,
            code=position.code,
            side=position.side,
            quantity=position.quantity,
            average_cost=position.average_cost,
            realized_profit_loss=position.realized_profit_loss,
            opened_at=position.opened_at.astimezone(timezone.utc),
        )

        try:
            with self._connect() as connection:
                cursor = connection.execute(
                    """
                    UPDATE positions
                    SET
                        quantity = ?,
                        average_cost = ?,
                        realized_profit_loss = ?,
                        opened_at = ?,
                        updated_at = ?
                    WHERE position_id = ?
                    """,
                    (
                        normalized_position.quantity,
                        normalized_position.average_cost,
                        normalized_position.realized_profit_loss,
                        normalized_position.opened_at.isoformat(),
                        current_time.isoformat(),
                        normalized_position.position_id,
                    ),
                )
                connection.commit()

                if cursor.rowcount != 1:
                    raise PositionNotFoundError(
                        "更新対象ポジションが存在しません。 "
                        f"position_id={normalized_position.position_id}"
                    )
        except PositionNotFoundError:
            raise
        except sqlite3.Error as error:
            raise PositionRepositoryError(
                "ポジションを更新できませんでした。 "
                f"position_id={normalized_position.position_id}"
            ) from error

        return self.get(normalized_position.position_id)


    def delete(
        self,
        position_id: str,
    ) -> TradingPositionRecord:
        """現在ポジションを削除し、削除前レコードを返す。"""

        current = self.get(position_id)

        try:
            with self._connect() as connection:
                cursor = connection.execute(
                    """
                    DELETE FROM positions
                    WHERE position_id = ?
                    """,
                    (current.position_id,),
                )
                connection.commit()

                if cursor.rowcount != 1:
                    raise PositionNotFoundError(
                        "削除対象ポジションが存在しません。 "
                        f"position_id={current.position_id}"
                    )
        except PositionNotFoundError:
            raise
        except sqlite3.Error as error:
            raise PositionRepositoryError(
                "ポジションを削除できませんでした。 "
                f"position_id={current.position_id}"
            ) from error

        return current

    def list_recent(
        self,
        *,
        limit: int = 100,
        code: str | None = None,
        side: BrokerPositionSide | None = None,
    ) -> list[TradingPositionRecord]:
        """現在ポジションを更新日時の新しい順に返す。"""

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
                    ORDER BY updated_at DESC, id DESC
                    LIMIT ?
                    """,
                    parameters,
                ).fetchall()
        except sqlite3.Error as error:
            raise PositionRepositoryError(
                "ポジション一覧を読み込めませんでした。"
            ) from error

        return [self._row_to_record(row) for row in rows]

    def count(
        self,
        *,
        code: str | None = None,
        side: BrokerPositionSide | None = None,
    ) -> int:
        """条件に一致する現在ポジション件数を返す。"""

        conditions: list[str] = []
        parameters: list[object] = []

        if code is not None:
            conditions.append("code = ?")
            parameters.append(self._normalize_code(code))

        if side is not None:
            conditions.append("side = ?")
            parameters.append(side.value)

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
                    FROM positions
                    {where_clause}
                    """,
                    parameters,
                ).fetchone()
        except sqlite3.Error as error:
            raise PositionRepositoryError(
                "ポジション件数を取得できませんでした。"
            ) from error

        return int(row[0]) if row is not None else 0

    def _connect(self) -> sqlite3.Connection:
        """SQLite接続を返す。"""

        return sqlite3.connect(self.database_path)

    def _current_time(self) -> datetime:
        """現在日時をUTCへ正規化する。"""

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
        """必須文字列を正規化する。"""

        normalized = value.strip()

        if not normalized:
            raise ValueError(
                f"{name}を指定してください。"
            )

        return normalized

    @classmethod
    def _normalize_code(cls, code: str) -> str:
        """銘柄コードを検証する。"""

        normalized = cls._normalize_required(
            code,
            "銘柄コード",
        )

        if not normalized.isdigit():
            raise ValueError(
                "銘柄コードは数字で指定してください。"
            )

        if len(normalized) not in {4, 5}:
            raise ValueError(
                "銘柄コードは4桁または5桁で指定してください。"
            )

        return normalized

    @staticmethod
    def _select_sql() -> str:
        """ポジション取得用SELECT文を返す。"""

        return """
            SELECT
                id,
                position_id,
                code,
                side,
                quantity,
                average_cost,
                realized_profit_loss,
                opened_at,
                created_at,
                updated_at
            FROM positions
        """

    @classmethod
    def _row_to_record(
        cls,
        row: tuple[object, ...],
    ) -> TradingPositionRecord:
        """SQLiteの1行をポジションへ変換する。"""

        position = TradingPosition(
            position_id=str(row[1]),
            code=str(row[2]),
            side=BrokerPositionSide(str(row[3])),
            quantity=int(row[4]),
            average_cost=float(row[5]),
            realized_profit_loss=float(row[6]),
            opened_at=cls._parse_datetime(str(row[7])),
        )

        return TradingPositionRecord(
            id=int(row[0]),
            position=position,
            created_at=cls._parse_datetime(str(row[8])),
            updated_at=cls._parse_datetime(str(row[9])),
        )

    @staticmethod
    def _parse_datetime(value: str) -> datetime:
        """SQLite日時文字列をUTC日時へ変換する。"""

        parsed = datetime.fromisoformat(value)

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)

        return parsed.astimezone(timezone.utc)
