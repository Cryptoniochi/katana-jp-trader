"""RecoveryEventをSQLiteへ永続化するRepository。"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from app.database import initialize_database
from app.runtime.recovery_event_models import (
    RecoveryEvent,
    RecoveryEventCategory,
    RecoveryEventStatus,
    RecoverySource,
)
from app.runtime.recovery_event_repository import (
    RecoveryEventRepository,
)


class SQLiteRecoveryEventRepository(
    RecoveryEventRepository
):
    """RecoveryEventをSQLiteへ保存するRepository。"""

    _DUPLICATE_EVENT_MESSAGE = (
        "RecoveryEvent with the same event_id "
        "already exists"
    )

    def __init__(
        self,
        database_path: Path,
    ) -> None:
        self.database_path = Path(database_path)
        initialize_database(self.database_path)

    def add(
        self,
        event: RecoveryEvent,
    ) -> RecoveryEvent:
        """RecoveryEventを保存する。"""

        self._validate_event(event)
        metadata_json = self._serialize_metadata(
            event.metadata
        )

        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO recovery_events (
                        event_id,
                        source,
                        category,
                        status,
                        name,
                        started_at,
                        completed_at,
                        message,
                        metadata_json,
                        created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    """,
                    (
                        event.event_id,
                        event.source.value,
                        event.category.value,
                        event.status.value,
                        event.name,
                        event.started_at.isoformat(),
                        (
                            None
                            if event.completed_at is None
                            else event.completed_at.isoformat()
                        ),
                        event.message,
                        metadata_json,
                    ),
                )
                connection.commit()
        except sqlite3.IntegrityError as error:
            if self.get_by_id(event.event_id) is not None:
                raise ValueError(
                    self._DUPLICATE_EVENT_MESSAGE
                ) from error
            raise

        return event

    def list_all(
        self,
    ) -> tuple[RecoveryEvent, ...]:
        """すべてのRecoveryEventを時系列順で返す。"""

        with self._connect() as connection:
            rows = connection.execute(
                f"""
                {self._select_columns()}
                ORDER BY
                    started_at ASC,
                    COALESCE(completed_at, started_at) ASC,
                    event_id ASC
                """
            ).fetchall()

        return tuple(
            self._event_from_row(row)
            for row in rows
        )

    def list_by_source(
        self,
        source: RecoverySource,
    ) -> tuple[RecoveryEvent, ...]:
        """指定した発生元のRecoveryEventを返す。"""

        self._validate_source(source)
        return self._list_where(
            "source = ?",
            (source.value,),
        )

    def list_by_category(
        self,
        category: RecoveryEventCategory,
    ) -> tuple[RecoveryEvent, ...]:
        """指定分類のRecoveryEventを返す。"""

        self._validate_category(category)
        return self._list_where(
            "category = ?",
            (category.value,),
        )

    def list_by_status(
        self,
        status: RecoveryEventStatus,
    ) -> tuple[RecoveryEvent, ...]:
        """指定状態のRecoveryEventを返す。"""

        self._validate_status(status)
        return self._list_where(
            "status = ?",
            (status.value,),
        )

    def get_by_id(
        self,
        event_id: str,
    ) -> RecoveryEvent | None:
        """Event IDに一致するRecoveryEventを返す。"""

        normalized_event_id = self._normalize_event_id(
            event_id
        )

        with self._connect() as connection:
            row = connection.execute(
                f"""
                {self._select_columns()}
                WHERE event_id = ?
                LIMIT 1
                """,
                (normalized_event_id,),
            ).fetchone()

        if row is None:
            return None

        return self._event_from_row(row)

    def latest(
        self,
        *,
        source: RecoverySource | None = None,
    ) -> RecoveryEvent | None:
        """最新のRecoveryEventを返す。"""

        if source is not None:
            self._validate_source(source)

        query = self._select_columns()
        parameters: tuple[object, ...] = ()

        if source is not None:
            query += "\nWHERE source = ?"
            parameters = (source.value,)

        query += """
            ORDER BY
                started_at DESC,
                COALESCE(completed_at, started_at) DESC,
                event_id DESC
            LIMIT 1
        """

        with self._connect() as connection:
            row = connection.execute(
                query,
                parameters,
            ).fetchone()

        if row is None:
            return None

        return self._event_from_row(row)

    def count(
        self,
        *,
        source: RecoverySource | None = None,
        category: RecoveryEventCategory | None = None,
        status: RecoveryEventStatus | None = None,
    ) -> int:
        """条件に一致するRecoveryEvent件数を返す。"""

        if source is not None:
            self._validate_source(source)
        if category is not None:
            self._validate_category(category)
        if status is not None:
            self._validate_status(status)

        conditions: list[str] = []
        parameters: list[object] = []

        if source is not None:
            conditions.append("source = ?")
            parameters.append(source.value)
        if category is not None:
            conditions.append("category = ?")
            parameters.append(category.value)
        if status is not None:
            conditions.append("status = ?")
            parameters.append(status.value)

        query = "SELECT COUNT(*) FROM recovery_events"
        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        with self._connect() as connection:
            row = connection.execute(
                query,
                tuple(parameters),
            ).fetchone()

        if row is None:
            return 0

        return int(row[0])

    def clear(self) -> None:
        """すべてのRecoveryEventを削除する。"""

        with self._connect() as connection:
            connection.execute(
                "DELETE FROM recovery_events"
            )
            connection.commit()

    def _list_where(
        self,
        condition: str,
        parameters: tuple[object, ...],
    ) -> tuple[RecoveryEvent, ...]:
        """指定条件のEventを時系列順で返す。"""

        with self._connect() as connection:
            rows = connection.execute(
                f"""
                {self._select_columns()}
                WHERE {condition}
                ORDER BY
                    started_at ASC,
                    COALESCE(completed_at, started_at) ASC,
                    event_id ASC
                """,
                parameters,
            ).fetchall()

        return tuple(
            self._event_from_row(row)
            for row in rows
        )

    def _connect(self) -> sqlite3.Connection:
        """SQLite接続を返す。"""

        connection = sqlite3.connect(
            self.database_path
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @staticmethod
    def _select_columns() -> str:
        """RecoveryEvent取得用のSELECT句を返す。"""

        return """
            SELECT
                event_id,
                source,
                category,
                status,
                name,
                started_at,
                completed_at,
                message,
                metadata_json
            FROM recovery_events
        """

    @classmethod
    def _event_from_row(
        cls,
        row: sqlite3.Row,
    ) -> RecoveryEvent:
        """SQLite RowをRecoveryEventへ変換する。"""

        completed_at_value = row["completed_at"]

        return RecoveryEvent(
            event_id=str(row["event_id"]),
            source=RecoverySource(row["source"]),
            category=RecoveryEventCategory(
                row["category"]
            ),
            status=RecoveryEventStatus(row["status"]),
            name=str(row["name"]),
            started_at=cls._parse_datetime(
                row["started_at"]
            ),
            completed_at=(
                None
                if completed_at_value is None
                else cls._parse_datetime(
                    completed_at_value
                )
            ),
            message=row["message"],
            metadata=cls._deserialize_metadata(
                str(row["metadata_json"])
            ),
        )

    @staticmethod
    def _parse_datetime(value: object) -> datetime:
        """ISO 8601文字列をdatetimeへ変換する。"""

        return datetime.fromisoformat(str(value))

    @classmethod
    def _serialize_metadata(
        cls,
        metadata: Mapping[str, object],
    ) -> str:
        """Metadataを型情報付きJSONへ変換する。"""

        try:
            return json.dumps(
                cls._to_json_value(metadata),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        except (TypeError, ValueError) as error:
            raise TypeError(
                "metadata must contain JSON-compatible values"
            ) from error

    @classmethod
    def _to_json_value(cls, value: object) -> Any:
        """Tupleを保持しながらJSON互換値へ変換する。"""

        if value is None or isinstance(
            value,
            (str, int, float, bool),
        ):
            return value

        if isinstance(value, tuple):
            return {
                "__katana_type__": "tuple",
                "items": [
                    cls._to_json_value(item)
                    for item in value
                ],
            }

        if isinstance(value, list):
            return [
                cls._to_json_value(item)
                for item in value
            ]

        if isinstance(value, Mapping):
            return {
                str(key): cls._to_json_value(item)
                for key, item in value.items()
            }

        raise TypeError(
            f"unsupported metadata value: {type(value).__name__}"
        )

    @classmethod
    def _deserialize_metadata(
        cls,
        metadata_json: str,
    ) -> Mapping[str, object]:
        """型情報付きJSONをMetadataへ復元する。"""

        raw_value = json.loads(metadata_json)
        restored = cls._from_json_value(raw_value)

        if not isinstance(restored, dict):
            raise ValueError(
                "metadata_json must represent an object"
            )

        return restored

    @classmethod
    def _from_json_value(cls, value: Any) -> object:
        """型情報付きJSON値をPython値へ復元する。"""

        if isinstance(value, list):
            return [
                cls._from_json_value(item)
                for item in value
            ]

        if isinstance(value, dict):
            if (
                value.get("__katana_type__") == "tuple"
                and set(value) == {
                    "__katana_type__",
                    "items",
                }
            ):
                items = value["items"]
                if not isinstance(items, list):
                    raise ValueError(
                        "tuple metadata items must be a list"
                    )
                return tuple(
                    cls._from_json_value(item)
                    for item in items
                )

            return {
                str(key): cls._from_json_value(item)
                for key, item in value.items()
            }

        return value

    @staticmethod
    def _validate_source(source: RecoverySource) -> None:
        """RecoverySource以外を拒否する。"""

        if not isinstance(source, RecoverySource):
            raise TypeError(
                "source must be a RecoverySource"
            )

    @staticmethod
    def _validate_category(
        category: RecoveryEventCategory,
    ) -> None:
        """RecoveryEventCategory以外を拒否する。"""

        if not isinstance(
            category,
            RecoveryEventCategory,
        ):
            raise TypeError(
                "category must be a RecoveryEventCategory"
            )

    @staticmethod
    def _validate_status(
        status: RecoveryEventStatus,
    ) -> None:
        """RecoveryEventStatus以外を拒否する。"""

        if not isinstance(status, RecoveryEventStatus):
            raise TypeError(
                "status must be a RecoveryEventStatus"
            )
