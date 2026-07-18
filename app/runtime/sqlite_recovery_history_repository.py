"""Recovery履歴をSQLiteへ永続化するRepository。"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from app.database import initialize_database
from app.runtime.recovery_history_models import (
    RecoveryComponent,
    RecoveryHistoryEntry,
)
from app.runtime.recovery_history_repository import (
    RecoveryHistoryRepository,
)
from app.runtime.recovery_models import (
    RecoveryAttempt,
    RecoveryResult,
    RecoveryStatus,
)


class SQLiteRecoveryHistoryRepository(
    RecoveryHistoryRepository
):
    """Recovery履歴をSQLiteへ保存するRepository。

    既存のRecoveryHistoryRepositoryと同じ公開インターフェースを持ち、
    別プロセスから同じSQLiteファイルを参照できるようにする。

    必要なテーブルはKATANA共通のinitialize_databaseで初期化する。
    """

    def __init__(
        self,
        database_path: Path,
    ) -> None:
        self.database_path = Path(database_path)
        initialize_database(self.database_path)

    def add(
        self,
        entry: RecoveryHistoryEntry,
    ) -> None:
        """Recovery履歴と全試行結果を保存する。"""

        if not isinstance(entry, RecoveryHistoryEntry):
            raise TypeError(
                "entry must be a RecoveryHistoryEntry"
            )

        result = entry.result

        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO recovery_history (
                    component,
                    recovery_name,
                    status,
                    started_at,
                    completed_at,
                    message,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (
                    entry.component.value,
                    result.recovery_name,
                    result.status.value,
                    result.started_at.isoformat(),
                    result.completed_at.isoformat(),
                    result.message,
                ),
            )

            history_id = cursor.lastrowid

            if history_id is None:
                raise RuntimeError(
                    "Recovery履歴IDを取得できませんでした。"
                )

            for attempt in result.attempts:
                connection.execute(
                    """
                    INSERT INTO recovery_attempts (
                        recovery_history_id,
                        attempt_number,
                        started_at,
                        completed_at,
                        successful,
                        error_message,
                        delay_seconds_before_attempt,
                        created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    """,
                    (
                        history_id,
                        attempt.attempt_number,
                        attempt.started_at.isoformat(),
                        attempt.completed_at.isoformat(),
                        1 if attempt.successful else 0,
                        attempt.error_message,
                        attempt.delay_seconds_before_attempt,
                    ),
                )

            connection.commit()

    def list_all(
        self,
    ) -> tuple[RecoveryHistoryEntry, ...]:
        """保存されている全履歴を完了日時順で返す。"""

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    id,
                    component,
                    recovery_name,
                    status,
                    started_at,
                    completed_at,
                    message
                FROM recovery_history
                ORDER BY completed_at ASC, id ASC
                """
            ).fetchall()

            return tuple(
                self._entry_from_row(
                    connection=connection,
                    row=row,
                )
                for row in rows
            )

    def list_by_component(
        self,
        component: RecoveryComponent,
    ) -> tuple[RecoveryHistoryEntry, ...]:
        """指定コンポーネントの履歴を返す。"""

        self._validate_component(component)

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    id,
                    component,
                    recovery_name,
                    status,
                    started_at,
                    completed_at,
                    message
                FROM recovery_history
                WHERE component = ?
                ORDER BY completed_at ASC, id ASC
                """,
                (component.value,),
            ).fetchall()

            return tuple(
                self._entry_from_row(
                    connection=connection,
                    row=row,
                )
                for row in rows
            )

    def latest(
        self,
        component: RecoveryComponent | None = None,
    ) -> RecoveryHistoryEntry | None:
        """最新のRecovery履歴を返す。"""

        if component is not None:
            self._validate_component(component)

        query = """
            SELECT
                id,
                component,
                recovery_name,
                status,
                started_at,
                completed_at,
                message
            FROM recovery_history
        """
        parameters: tuple[object, ...] = ()

        if component is not None:
            query += """
                WHERE component = ?
            """
            parameters = (component.value,)

        query += """
            ORDER BY completed_at DESC, id DESC
            LIMIT 1
        """

        with self._connect() as connection:
            row = connection.execute(
                query,
                parameters,
            ).fetchone()

            if row is None:
                return None

            return self._entry_from_row(
                connection=connection,
                row=row,
            )

    def count(
        self,
        component: RecoveryComponent | None = None,
    ) -> int:
        """保存済み履歴件数を返す。"""

        if component is not None:
            self._validate_component(component)

        query = """
            SELECT COUNT(*)
            FROM recovery_history
        """
        parameters: tuple[object, ...] = ()

        if component is not None:
            query += """
                WHERE component = ?
            """
            parameters = (component.value,)

        with self._connect() as connection:
            row = connection.execute(
                query,
                parameters,
            ).fetchone()

        if row is None:
            return 0

        return int(row[0])

    def clear(self) -> None:
        """保存済みRecovery履歴をすべて削除する。"""

        with self._connect() as connection:
            connection.execute(
                """
                DELETE FROM recovery_history
                """
            )
            connection.commit()

    def _connect(self) -> sqlite3.Connection:
        """Foreign Keyを有効化したSQLite接続を返す。"""

        connection = sqlite3.connect(
            self.database_path
        )
        connection.row_factory = sqlite3.Row
        connection.execute(
            "PRAGMA foreign_keys = ON"
        )
        return connection

    def _entry_from_row(
        self,
        *,
        connection: sqlite3.Connection,
        row: sqlite3.Row,
    ) -> RecoveryHistoryEntry:
        """SQLite RowをRecoveryHistoryEntryへ変換する。"""

        attempt_rows = connection.execute(
            """
            SELECT
                attempt_number,
                started_at,
                completed_at,
                successful,
                error_message,
                delay_seconds_before_attempt
            FROM recovery_attempts
            WHERE recovery_history_id = ?
            ORDER BY attempt_number ASC
            """,
            (int(row["id"]),),
        ).fetchall()

        attempts = tuple(
            RecoveryAttempt(
                attempt_number=int(
                    attempt_row["attempt_number"]
                ),
                started_at=self._parse_datetime(
                    attempt_row["started_at"]
                ),
                completed_at=self._parse_datetime(
                    attempt_row["completed_at"]
                ),
                successful=bool(
                    attempt_row["successful"]
                ),
                error_message=attempt_row[
                    "error_message"
                ],
                delay_seconds_before_attempt=float(
                    attempt_row[
                        "delay_seconds_before_attempt"
                    ]
                ),
            )
            for attempt_row in attempt_rows
        )

        result = RecoveryResult(
            recovery_name=str(
                row["recovery_name"]
            ),
            status=RecoveryStatus(
                row["status"]
            ),
            started_at=self._parse_datetime(
                row["started_at"]
            ),
            completed_at=self._parse_datetime(
                row["completed_at"]
            ),
            attempts=attempts,
            message=row["message"],
        )

        return RecoveryHistoryEntry(
            component=RecoveryComponent(
                row["component"]
            ),
            result=result,
        )

    @staticmethod
    def _parse_datetime(
        value: object,
    ) -> datetime:
        """ISO 8601文字列をdatetimeへ変換する。"""

        return datetime.fromisoformat(
            str(value)
        )

    @staticmethod
    def _validate_component(
        component: RecoveryComponent,
    ) -> None:
        """RecoveryComponent以外を拒否する。"""

        if not isinstance(component, RecoveryComponent):
            raise TypeError(
                "component must be a RecoveryComponent"
            )
