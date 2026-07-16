"""定刻処理の完了状態をSQLiteへ永続化する。"""

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path


class ScheduledRunStateRepositoryError(RuntimeError):
    """定刻実行状態Repositoryの基底例外。"""


class ScheduledRunStateNotFoundError(
    ScheduledRunStateRepositoryError
):
    """指定された定刻実行状態が存在しないことを表す。"""


@dataclass(frozen=True, slots=True)
class ScheduledRunStateRecord:
    """SQLiteへ保存された定刻処理の完了状態。"""

    id: int
    trading_date: date
    process_name: str
    completed_at: datetime
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        """保存済み完了状態の整合性を検証する。"""

        if self.id <= 0:
            raise ValueError(
                "保存IDは0より大きい必要があります。"
            )

        normalized_process_name = self.process_name.strip()

        if not normalized_process_name:
            raise ValueError(
                "処理名を指定してください。"
            )

        for name, value in {
            "完了日時": self.completed_at,
            "作成日時": self.created_at,
            "更新日時": self.updated_at,
        }.items():
            if value.tzinfo is None:
                raise ValueError(
                    f"{name}にはタイムゾーンが必要です。"
                )

        if self.updated_at < self.created_at:
            raise ValueError(
                "更新日時は作成日時以後である必要があります。"
            )

        object.__setattr__(
            self,
            "process_name",
            normalized_process_name,
        )


class ScheduledRunStateRepository:
    """定刻処理の完了状態をSQLiteで管理する。"""

    def __init__(
        self,
        database_path: Path,
    ) -> None:
        """DBパスを設定する。"""

        self.database_path = database_path

    def has_completed(
        self,
        *,
        trading_date: date,
        process_name: str,
    ) -> bool:
        """指定日・処理名が完了済みか返す。"""

        normalized_process_name = self._normalize_process_name(
            process_name
        )

        try:
            with self._connect() as connection:
                row = connection.execute(
                    """
                    SELECT 1
                    FROM scheduled_run_states
                    WHERE trading_date = ?
                      AND process_name = ?
                    LIMIT 1
                    """,
                    (
                        trading_date.isoformat(),
                        normalized_process_name,
                    ),
                ).fetchone()
        except sqlite3.Error as error:
            raise ScheduledRunStateRepositoryError(
                "定刻処理の完了状態を確認できませんでした。 "
                f"trading_date={trading_date.isoformat()} "
                f"process_name={normalized_process_name}"
            ) from error

        return row is not None

    def mark_completed(
        self,
        *,
        trading_date: date,
        process_name: str,
        completed_at: datetime,
    ) -> None:
        """指定日・処理名を完了済みとして保存する。

        同一日・同一処理が既に存在する場合は、
        最初の完了状態を維持して正常終了する。
        """

        normalized_process_name = self._normalize_process_name(
            process_name
        )
        normalized_completed_at = self._normalize_datetime(
            completed_at,
            "完了日時",
        )
        timestamp_text = normalized_completed_at.isoformat()

        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO scheduled_run_states (
                        trading_date,
                        process_name,
                        completed_at,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(
                        trading_date,
                        process_name
                    )
                    DO NOTHING
                    """,
                    (
                        trading_date.isoformat(),
                        normalized_process_name,
                        timestamp_text,
                        timestamp_text,
                        timestamp_text,
                    ),
                )
                connection.commit()
        except sqlite3.Error as error:
            raise ScheduledRunStateRepositoryError(
                "定刻処理の完了状態を保存できませんでした。 "
                f"trading_date={trading_date.isoformat()} "
                f"process_name={normalized_process_name}"
            ) from error

    def get(
        self,
        *,
        trading_date: date,
        process_name: str,
    ) -> ScheduledRunStateRecord:
        """指定日・処理名の完了状態を返す。"""

        normalized_process_name = self._normalize_process_name(
            process_name
        )

        try:
            with self._connect() as connection:
                row = connection.execute(
                    self._select_sql()
                    + """
                    WHERE trading_date = ?
                      AND process_name = ?
                    """,
                    (
                        trading_date.isoformat(),
                        normalized_process_name,
                    ),
                ).fetchone()
        except sqlite3.Error as error:
            raise ScheduledRunStateRepositoryError(
                "定刻処理の完了状態を読み込めませんでした。 "
                f"trading_date={trading_date.isoformat()} "
                f"process_name={normalized_process_name}"
            ) from error

        if row is None:
            raise ScheduledRunStateNotFoundError(
                "指定された定刻処理の完了状態が存在しません。 "
                f"trading_date={trading_date.isoformat()} "
                f"process_name={normalized_process_name}"
            )

        return self._row_to_record(row)

    def latest(
        self,
        *,
        process_name: str | None = None,
    ) -> ScheduledRunStateRecord | None:
        """条件に一致する最新の完了状態を返す。"""

        parameters: list[object] = []
        where_clause = ""

        if process_name is not None:
            where_clause = "WHERE process_name = ?"
            parameters.append(
                self._normalize_process_name(process_name)
            )

        try:
            with self._connect() as connection:
                row = connection.execute(
                    self._select_sql()
                    + f"""
                    {where_clause}
                    ORDER BY
                        trading_date DESC,
                        completed_at DESC,
                        id DESC
                    LIMIT 1
                    """,
                    parameters,
                ).fetchone()
        except sqlite3.Error as error:
            raise ScheduledRunStateRepositoryError(
                "最新の定刻処理完了状態を読み込めませんでした。"
            ) from error

        if row is None:
            return None

        return self._row_to_record(row)

    def list_recent(
        self,
        *,
        limit: int = 100,
        process_name: str | None = None,
    ) -> list[ScheduledRunStateRecord]:
        """完了状態を取引日の新しい順に返す。"""

        if limit <= 0:
            raise ValueError(
                "取得件数は0より大きい必要があります。"
            )

        parameters: list[object] = []
        where_clause = ""

        if process_name is not None:
            where_clause = "WHERE process_name = ?"
            parameters.append(
                self._normalize_process_name(process_name)
            )

        parameters.append(limit)

        try:
            with self._connect() as connection:
                rows = connection.execute(
                    self._select_sql()
                    + f"""
                    {where_clause}
                    ORDER BY
                        trading_date DESC,
                        completed_at DESC,
                        id DESC
                    LIMIT ?
                    """,
                    parameters,
                ).fetchall()
        except sqlite3.Error as error:
            raise ScheduledRunStateRepositoryError(
                "定刻処理完了状態の一覧を読み込めませんでした。"
            ) from error

        return [
            self._row_to_record(row)
            for row in rows
        ]

    def count(
        self,
        *,
        process_name: str | None = None,
    ) -> int:
        """条件に一致する完了状態件数を返す。"""

        parameters: list[object] = []
        where_clause = ""

        if process_name is not None:
            where_clause = "WHERE process_name = ?"
            parameters.append(
                self._normalize_process_name(process_name)
            )

        try:
            with self._connect() as connection:
                row = connection.execute(
                    f"""
                    SELECT COUNT(*)
                    FROM scheduled_run_states
                    {where_clause}
                    """,
                    parameters,
                ).fetchone()
        except sqlite3.Error as error:
            raise ScheduledRunStateRepositoryError(
                "定刻処理完了状態の件数を取得できませんでした。"
            ) from error

        return int(row[0]) if row is not None else 0

    def _connect(self) -> sqlite3.Connection:
        """SQLite接続を返す。"""

        return sqlite3.connect(self.database_path)

    @staticmethod
    def _normalize_process_name(
        process_name: str,
    ) -> str:
        """処理名を検証して正規化する。"""

        normalized_process_name = process_name.strip()

        if not normalized_process_name:
            raise ValueError(
                "処理名を指定してください。"
            )

        return normalized_process_name

    @staticmethod
    def _normalize_datetime(
        value: datetime,
        name: str,
    ) -> datetime:
        """日時をUTCへ正規化する。"""

        if value.tzinfo is None:
            raise ValueError(
                f"{name}にはタイムゾーンが必要です。"
            )

        return value.astimezone(timezone.utc)

    @staticmethod
    def _select_sql() -> str:
        """完了状態取得用SELECT文を返す。"""

        return """
            SELECT
                id,
                trading_date,
                process_name,
                completed_at,
                created_at,
                updated_at
            FROM scheduled_run_states
        """

    @classmethod
    def _row_to_record(
        cls,
        row: tuple[object, ...],
    ) -> ScheduledRunStateRecord:
        """SQLiteの1行を完了状態へ変換する。"""

        return ScheduledRunStateRecord(
            id=int(row[0]),
            trading_date=date.fromisoformat(str(row[1])),
            process_name=str(row[2]),
            completed_at=cls._parse_datetime(str(row[3])),
            created_at=cls._parse_datetime(str(row[4])),
            updated_at=cls._parse_datetime(str(row[5])),
        )

    @staticmethod
    def _parse_datetime(value: str) -> datetime:
        """SQLite日時文字列をUTC日時へ変換する。"""

        parsed = datetime.fromisoformat(value)

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)

        return parsed.astimezone(timezone.utc)
