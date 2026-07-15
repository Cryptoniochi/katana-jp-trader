"""J-Quants自動更新の実行履歴をSQLiteへ保存する。"""

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from uuid import uuid4


class UpdateRunStatus(StrEnum):
    """自動更新の実行状態。"""

    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL_FAILURE = "partial_failure"
    FAILED = "failed"
    ALREADY_RUNNING = "already_running"

    @property
    def is_terminal(self) -> bool:
        """終了済み状態か返す。"""

        return self is not UpdateRunStatus.RUNNING

    @property
    def is_successful(self) -> bool:
        """正常終了状態か返す。"""

        return self is UpdateRunStatus.SUCCESS


@dataclass(frozen=True, slots=True)
class UpdateRunMetrics:
    """自動更新の件数情報。"""

    requested_code_count: int = 0
    updated_code_count: int = 0
    skipped_code_count: int = 0
    failed_code_count: int = 0

    business_date_count: int = 0

    request_count: int = 0
    successful_request_count: int = 0
    empty_request_count: int = 0
    failed_request_count: int = 0

    processed_bar_count: int = 0

    def __post_init__(self) -> None:
        """負の件数を拒否する。"""

        values = (
            self.requested_code_count,
            self.updated_code_count,
            self.skipped_code_count,
            self.failed_code_count,
            self.business_date_count,
            self.request_count,
            self.successful_request_count,
            self.empty_request_count,
            self.failed_request_count,
            self.processed_bar_count,
        )

        if any(value < 0 for value in values):
            raise ValueError(
                "実行履歴の件数は0以上である必要があります。"
            )

        if (
            self.updated_code_count
            + self.skipped_code_count
            + self.failed_code_count
            > self.requested_code_count
        ):
            raise ValueError(
                "更新・スキップ・失敗銘柄数の合計が"
                "対象銘柄数を超えています。"
            )

        if (
            self.successful_request_count
            + self.empty_request_count
            + self.failed_request_count
            > self.request_count
        ):
            raise ValueError(
                "成功・空・失敗リクエスト数の合計が"
                "総リクエスト数を超えています。"
            )


@dataclass(frozen=True, slots=True)
class UpdateRunRecord:
    """保存済みの自動更新実行履歴。"""

    id: int
    run_id: str
    process_name: str
    status: UpdateRunStatus

    started_at: datetime
    finished_at: datetime | None
    exit_code: int | None

    metrics: UpdateRunMetrics
    error_message: str | None

    @property
    def is_finished(self) -> bool:
        """実行が終了しているか返す。"""

        return self.finished_at is not None

    @property
    def duration_seconds(self) -> float | None:
        """実行時間を秒数で返す。"""

        if self.finished_at is None:
            return None

        return (
            self.finished_at - self.started_at
        ).total_seconds()


class UpdateRunRepositoryError(RuntimeError):
    """実行履歴Repositoryの処理失敗。"""


class UpdateRunNotFoundError(UpdateRunRepositoryError):
    """指定された実行履歴が存在しないことを表す。"""


class UpdateRunAlreadyFinishedError(UpdateRunRepositoryError):
    """終了済みの実行履歴を再終了しようとしたことを表す。"""


class UpdateRunRepository:
    """J-Quants自動更新の実行履歴を管理する。"""

    def __init__(
        self,
        database_path: Path,
        *,
        now_provider: Callable[[], datetime] | None = None,
        run_id_provider: Callable[[], str] | None = None,
    ) -> None:
        """DBパスと日時・ID生成処理を設定する。"""

        self.database_path = database_path
        self.now_provider = (
            now_provider
            if now_provider is not None
            else lambda: datetime.now(timezone.utc)
        )
        self.run_id_provider = (
            run_id_provider
            if run_id_provider is not None
            else lambda: uuid4().hex
        )

    def start(
        self,
        *,
        process_name: str,
        requested_code_count: int,
        run_id: str | None = None,
    ) -> UpdateRunRecord:
        """新しい自動更新実行履歴を開始状態で保存する。"""

        normalized_process_name = process_name.strip()

        if not normalized_process_name:
            raise ValueError(
                "プロセス名を指定してください。"
            )

        if requested_code_count < 0:
            raise ValueError(
                "対象銘柄数は0以上である必要があります。"
            )

        resolved_run_id = (
            run_id
            if run_id is not None
            else self.run_id_provider()
        ).strip()

        if not resolved_run_id:
            raise ValueError(
                "実行IDを指定してください。"
            )

        started_at = self._current_time()

        try:
            with sqlite3.connect(
                self.database_path
            ) as connection:
                cursor = connection.execute(
                    """
                    INSERT INTO update_runs (
                        run_id,
                        process_name,
                        status,
                        started_at,
                        requested_code_count,
                        created_at,
                        updated_at
                    )
                    VALUES (
                        ?,
                        ?,
                        ?,
                        ?,
                        ?,
                        ?,
                        ?
                    )
                    """,
                    (
                        resolved_run_id,
                        normalized_process_name,
                        UpdateRunStatus.RUNNING.value,
                        started_at.isoformat(),
                        requested_code_count,
                        started_at.isoformat(),
                        started_at.isoformat(),
                    ),
                )

                connection.commit()

                record_id = int(
                    cursor.lastrowid
                )

        except sqlite3.IntegrityError as error:
            raise UpdateRunRepositoryError(
                "同じ実行IDの履歴が既に存在します。 "
                f"run_id={resolved_run_id}"
            ) from error

        except sqlite3.Error as error:
            raise UpdateRunRepositoryError(
                "自動更新実行履歴を開始できませんでした。 "
                f"run_id={resolved_run_id}"
            ) from error

        return UpdateRunRecord(
            id=record_id,
            run_id=resolved_run_id,
            process_name=normalized_process_name,
            status=UpdateRunStatus.RUNNING,
            started_at=started_at,
            finished_at=None,
            exit_code=None,
            metrics=UpdateRunMetrics(
                requested_code_count=(
                    requested_code_count
                ),
            ),
            error_message=None,
        )

    def finish(
        self,
        run_id: str,
        *,
        status: UpdateRunStatus,
        exit_code: int,
        metrics: UpdateRunMetrics,
        error_message: str | None = None,
    ) -> UpdateRunRecord:
        """実行履歴を終了状態へ更新する。"""

        normalized_run_id = self._normalize_run_id(
            run_id
        )

        if not status.is_terminal:
            raise ValueError(
                "終了処理には終了済みステータスを指定してください。"
            )

        if exit_code < 0:
            raise ValueError(
                "終了コードは0以上である必要があります。"
            )

        normalized_error_message = (
            error_message.strip()
            if error_message is not None
            else None
        )

        if normalized_error_message == "":
            normalized_error_message = None

        current_record = self.get(
            normalized_run_id
        )

        if current_record.is_finished:
            raise UpdateRunAlreadyFinishedError(
                "終了済みの自動更新実行履歴は"
                "再更新できません。 "
                f"run_id={normalized_run_id}"
            )

        finished_at = self._current_time()

        if finished_at < current_record.started_at:
            raise ValueError(
                "終了日時は開始日時以後である必要があります。"
            )

        try:
            with sqlite3.connect(
                self.database_path
            ) as connection:
                cursor = connection.execute(
                    """
                    UPDATE update_runs
                    SET
                        status = ?,
                        finished_at = ?,
                        exit_code = ?,
                        requested_code_count = ?,
                        updated_code_count = ?,
                        skipped_code_count = ?,
                        failed_code_count = ?,
                        business_date_count = ?,
                        request_count = ?,
                        successful_request_count = ?,
                        empty_request_count = ?,
                        failed_request_count = ?,
                        processed_bar_count = ?,
                        error_message = ?,
                        updated_at = ?
                    WHERE run_id = ?
                      AND finished_at IS NULL
                    """,
                    (
                        status.value,
                        finished_at.isoformat(),
                        exit_code,
                        metrics.requested_code_count,
                        metrics.updated_code_count,
                        metrics.skipped_code_count,
                        metrics.failed_code_count,
                        metrics.business_date_count,
                        metrics.request_count,
                        metrics.successful_request_count,
                        metrics.empty_request_count,
                        metrics.failed_request_count,
                        metrics.processed_bar_count,
                        normalized_error_message,
                        finished_at.isoformat(),
                        normalized_run_id,
                    ),
                )

                connection.commit()

                if cursor.rowcount != 1:
                    raise UpdateRunAlreadyFinishedError(
                        "自動更新実行履歴を終了できませんでした。 "
                        f"run_id={normalized_run_id}"
                    )

        except UpdateRunAlreadyFinishedError:
            raise

        except sqlite3.Error as error:
            raise UpdateRunRepositoryError(
                "自動更新実行履歴を終了できませんでした。 "
                f"run_id={normalized_run_id}"
            ) from error

        return self.get(
            normalized_run_id
        )

    def get(
        self,
        run_id: str,
    ) -> UpdateRunRecord:
        """実行IDに一致する履歴を返す。"""

        normalized_run_id = self._normalize_run_id(
            run_id
        )

        try:
            with sqlite3.connect(
                self.database_path
            ) as connection:
                row = connection.execute(
                    self._select_sql()
                    + """
                    WHERE run_id = ?
                    """,
                    (normalized_run_id,),
                ).fetchone()

        except sqlite3.Error as error:
            raise UpdateRunRepositoryError(
                "自動更新実行履歴を読み込めませんでした。 "
                f"run_id={normalized_run_id}"
            ) from error

        if row is None:
            raise UpdateRunNotFoundError(
                "指定された自動更新実行履歴が"
                "存在しません。 "
                f"run_id={normalized_run_id}"
            )

        return self._row_to_record(
            row
        )

    def latest(
        self,
    ) -> UpdateRunRecord | None:
        """開始日時が最新の実行履歴を返す。"""

        try:
            with sqlite3.connect(
                self.database_path
            ) as connection:
                row = connection.execute(
                    self._select_sql()
                    + """
                    ORDER BY started_at DESC, id DESC
                    LIMIT 1
                    """
                ).fetchone()

        except sqlite3.Error as error:
            raise UpdateRunRepositoryError(
                "最新の自動更新実行履歴を"
                "読み込めませんでした。"
            ) from error

        if row is None:
            return None

        return self._row_to_record(
            row
        )

    def list_recent(
        self,
        *,
        limit: int = 20,
        status: UpdateRunStatus | None = None,
    ) -> list[UpdateRunRecord]:
        """新しい順に実行履歴を返す。"""

        if limit <= 0:
            raise ValueError(
                "取得件数は0より大きい必要があります。"
            )

        parameters: list[object] = []
        where_clause = ""

        if status is not None:
            where_clause = "WHERE status = ?"
            parameters.append(
                status.value
            )

        parameters.append(
            limit
        )

        try:
            with sqlite3.connect(
                self.database_path
            ) as connection:
                rows = connection.execute(
                    self._select_sql()
                    + f"""
                    {where_clause}
                    ORDER BY started_at DESC, id DESC
                    LIMIT ?
                    """,
                    parameters,
                ).fetchall()

        except sqlite3.Error as error:
            raise UpdateRunRepositoryError(
                "自動更新実行履歴一覧を"
                "読み込めませんでした。"
            ) from error

        return [
            self._row_to_record(row)
            for row in rows
        ]

    def count(
        self,
        *,
        status: UpdateRunStatus | None = None,
    ) -> int:
        """条件に一致する実行履歴件数を返す。"""

        parameters: list[object] = []
        where_clause = ""

        if status is not None:
            where_clause = "WHERE status = ?"
            parameters.append(
                status.value
            )

        try:
            with sqlite3.connect(
                self.database_path
            ) as connection:
                row = connection.execute(
                    f"""
                    SELECT COUNT(*)
                    FROM update_runs
                    {where_clause}
                    """,
                    parameters,
                ).fetchone()

        except sqlite3.Error as error:
            raise UpdateRunRepositoryError(
                "自動更新実行履歴件数を"
                "取得できませんでした。"
            ) from error

        if row is None:
            return 0

        return int(
            row[0]
        )

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
    def _normalize_run_id(
        run_id: str,
    ) -> str:
        """実行IDを検証し前後空白を除去する。"""

        normalized_run_id = run_id.strip()

        if not normalized_run_id:
            raise ValueError(
                "実行IDを指定してください。"
            )

        return normalized_run_id

    @staticmethod
    def _select_sql() -> str:
        """実行履歴取得用SELECT文を返す。"""

        return """
            SELECT
                id,
                run_id,
                process_name,
                status,
                started_at,
                finished_at,
                exit_code,
                requested_code_count,
                updated_code_count,
                skipped_code_count,
                failed_code_count,
                business_date_count,
                request_count,
                successful_request_count,
                empty_request_count,
                failed_request_count,
                processed_bar_count,
                error_message
            FROM update_runs
        """

    @staticmethod
    def _row_to_record(
        row: tuple[object, ...],
    ) -> UpdateRunRecord:
        """SQLiteの行を実行履歴へ変換する。"""

        finished_at = (
            datetime.fromisoformat(
                str(row[5])
            )
            if row[5] is not None
            else None
        )

        exit_code = (
            int(row[6])
            if row[6] is not None
            else None
        )

        error_message = (
            str(row[17])
            if row[17] is not None
            else None
        )

        return UpdateRunRecord(
            id=int(row[0]),
            run_id=str(row[1]),
            process_name=str(row[2]),
            status=UpdateRunStatus(
                str(row[3])
            ),
            started_at=datetime.fromisoformat(
                str(row[4])
            ),
            finished_at=finished_at,
            exit_code=exit_code,
            metrics=UpdateRunMetrics(
                requested_code_count=int(row[7]),
                updated_code_count=int(row[8]),
                skipped_code_count=int(row[9]),
                failed_code_count=int(row[10]),
                business_date_count=int(row[11]),
                request_count=int(row[12]),
                successful_request_count=int(row[13]),
                empty_request_count=int(row[14]),
                failed_request_count=int(row[15]),
                processed_bar_count=int(row[16]),
            ),
            error_message=error_message,
        )