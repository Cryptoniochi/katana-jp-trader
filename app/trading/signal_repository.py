"""売買シグナルをSQLiteへ保存・取得するRepository。"""

import json
import sqlite3
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.trading.signal_models import (
    SignalAction,
    SignalStatus,
    TradeSignal,
    TradeSignalRecord,
)


class SignalRepositoryError(RuntimeError):
    """売買シグナルRepositoryの基底例外。"""


class SignalNotFoundError(SignalRepositoryError):
    """指定された売買シグナルが存在しないことを表す。"""


class DuplicateSignalError(SignalRepositoryError):
    """同一シグナルが既に保存されていることを表す。"""


class SignalStateTransitionError(SignalRepositoryError):
    """許可されないシグナル状態遷移を表す。"""


class SignalRepository:
    """売買シグナルをSQLiteで管理する。"""

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

    def save(
        self,
        signal: TradeSignal,
    ) -> TradeSignalRecord:
        """売買シグナルを未処理状態で保存する。"""

        current_time = self._current_time()
        metadata_json = self._serialize_metadata(
            signal.metadata,
        )

        try:
            with sqlite3.connect(
                self.database_path,
            ) as connection:
                cursor = connection.execute(
                    """
                    INSERT INTO trade_signals (
                        signal_id,
                        code,
                        strategy_name,
                        action,
                        generated_at,
                        signal_price,
                        quantity,
                        reason,
                        confidence,
                        metadata_json,
                        status,
                        processed_at,
                        process_note,
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
                        ?,
                        ?,
                        ?,
                        ?,
                        ?,
                        NULL,
                        NULL,
                        ?,
                        ?
                    )
                    """,
                    (
                        signal.signal_id,
                        signal.code,
                        signal.strategy_name,
                        signal.action.value,
                        (
                            signal.generated_at
                            .astimezone(timezone.utc)
                            .isoformat()
                        ),
                        signal.signal_price,
                        signal.quantity,
                        signal.reason,
                        signal.confidence,
                        metadata_json,
                        SignalStatus.PENDING.value,
                        current_time.isoformat(),
                        current_time.isoformat(),
                    ),
                )

                connection.commit()

                record_id = int(
                    cursor.lastrowid,
                )

        except sqlite3.IntegrityError as error:
            raise DuplicateSignalError(
                "同一の売買シグナルが既に存在します。 "
                f"signal_id={signal.signal_id} "
                f"code={signal.code} "
                f"strategy={signal.strategy_name} "
                f"action={signal.action.value} "
                f"generated_at="
                f"{signal.generated_at.isoformat()}"
            ) from error

        except sqlite3.Error as error:
            raise SignalRepositoryError(
                "売買シグナルを保存できませんでした。 "
                f"signal_id={signal.signal_id}"
            ) from error

        return self._create_record(
            record_id=record_id,
            signal=signal,
            status=SignalStatus.PENDING,
            processed_at=None,
            process_note=None,
            created_at=current_time,
            updated_at=current_time,
        )

    def get(
        self,
        signal_id: str,
    ) -> TradeSignalRecord:
        """シグナルIDに一致する保存済みシグナルを返す。"""

        normalized_signal_id = self._normalize_signal_id(
            signal_id,
        )

        try:
            with sqlite3.connect(
                self.database_path,
            ) as connection:
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
            raise SignalRepositoryError(
                "売買シグナルを読み込めませんでした。 "
                f"signal_id={normalized_signal_id}"
            ) from error

        if row is None:
            raise SignalNotFoundError(
                "指定された売買シグナルが存在しません。 "
                f"signal_id={normalized_signal_id}"
            )

        return self._row_to_record(
            row,
        )

    def latest(
        self,
        *,
        code: str | None = None,
        strategy_name: str | None = None,
        status: SignalStatus | None = None,
    ) -> TradeSignalRecord | None:
        """条件に一致する最新シグナルを返す。"""

        records = self.list_recent(
            limit=1,
            code=code,
            strategy_name=strategy_name,
            status=status,
        )

        if not records:
            return None

        return records[0]

    def list_recent(
        self,
        *,
        limit: int = 100,
        code: str | None = None,
        strategy_name: str | None = None,
        status: SignalStatus | None = None,
        action: SignalAction | None = None,
    ) -> list[TradeSignalRecord]:
        """条件に一致するシグナルを新しい順に返す。"""

        if limit <= 0:
            raise ValueError(
                "取得件数は0より大きい必要があります。"
            )

        conditions: list[str] = []
        parameters: list[object] = []

        if code is not None:
            conditions.append(
                "code = ?",
            )
            parameters.append(
                self._normalize_code(code),
            )

        if strategy_name is not None:
            conditions.append(
                "strategy_name = ?",
            )
            parameters.append(
                self._normalize_strategy_name(
                    strategy_name,
                ),
            )

        if status is not None:
            conditions.append(
                "status = ?",
            )
            parameters.append(
                status.value,
            )

        if action is not None:
            conditions.append(
                "action = ?",
            )
            parameters.append(
                action.value,
            )

        where_clause = ""

        if conditions:
            where_clause = (
                "WHERE "
                + " AND ".join(conditions)
            )

        parameters.append(
            limit,
        )

        try:
            with sqlite3.connect(
                self.database_path,
            ) as connection:
                rows = connection.execute(
                    self._select_sql()
                    + f"""
                    {where_clause}
                    ORDER BY generated_at DESC, id DESC
                    LIMIT ?
                    """,
                    parameters,
                ).fetchall()

        except sqlite3.Error as error:
            raise SignalRepositoryError(
                "売買シグナル一覧を読み込めませんでした。"
            ) from error

        return [
            self._row_to_record(row)
            for row in rows
        ]

    def list_pending(
        self,
        *,
        limit: int = 100,
        code: str | None = None,
        strategy_name: str | None = None,
    ) -> list[TradeSignalRecord]:
        """未処理シグナルを新しい順に返す。"""

        return self.list_recent(
            limit=limit,
            code=code,
            strategy_name=strategy_name,
            status=SignalStatus.PENDING,
        )

    def mark_processed(
        self,
        signal_id: str,
        *,
        process_note: str | None = None,
    ) -> TradeSignalRecord:
        """未処理シグナルを処理済みに更新する。"""

        return self._finish_signal(
            signal_id=signal_id,
            target_status=SignalStatus.PROCESSED,
            process_note=process_note,
        )

    def cancel(
        self,
        signal_id: str,
        *,
        process_note: str | None = None,
    ) -> TradeSignalRecord:
        """未処理シグナルを取消済みに更新する。"""

        return self._finish_signal(
            signal_id=signal_id,
            target_status=SignalStatus.CANCELLED,
            process_note=process_note,
        )

    def count(
        self,
        *,
        code: str | None = None,
        strategy_name: str | None = None,
        status: SignalStatus | None = None,
        action: SignalAction | None = None,
    ) -> int:
        """条件に一致するシグナル件数を返す。"""

        conditions: list[str] = []
        parameters: list[object] = []

        if code is not None:
            conditions.append(
                "code = ?",
            )
            parameters.append(
                self._normalize_code(code),
            )

        if strategy_name is not None:
            conditions.append(
                "strategy_name = ?",
            )
            parameters.append(
                self._normalize_strategy_name(
                    strategy_name,
                ),
            )

        if status is not None:
            conditions.append(
                "status = ?",
            )
            parameters.append(
                status.value,
            )

        if action is not None:
            conditions.append(
                "action = ?",
            )
            parameters.append(
                action.value,
            )

        where_clause = ""

        if conditions:
            where_clause = (
                "WHERE "
                + " AND ".join(conditions)
            )

        try:
            with sqlite3.connect(
                self.database_path,
            ) as connection:
                row = connection.execute(
                    f"""
                    SELECT COUNT(*)
                    FROM trade_signals
                    {where_clause}
                    """,
                    parameters,
                ).fetchone()

        except sqlite3.Error as error:
            raise SignalRepositoryError(
                "売買シグナル件数を取得できませんでした。"
            ) from error

        if row is None:
            return 0

        return int(
            row[0],
        )

    def _finish_signal(
        self,
        *,
        signal_id: str,
        target_status: SignalStatus,
        process_note: str | None,
    ) -> TradeSignalRecord:
        """未処理シグナルを終了状態へ更新する。"""

        normalized_signal_id = self._normalize_signal_id(
            signal_id,
        )

        if not target_status.is_terminal:
            raise ValueError(
                "終了状態を指定してください。"
            )

        current_record = self.get(
            normalized_signal_id,
        )

        if not current_record.is_pending:
            raise SignalStateTransitionError(
                "未処理ではない売買シグナルは"
                "状態変更できません。 "
                f"signal_id={normalized_signal_id} "
                f"status={current_record.status.value}"
            )

        normalized_process_note = (
            process_note.strip()
            if process_note is not None
            else None
        )

        if normalized_process_note == "":
            normalized_process_note = None

        processed_at = self._current_time()

        if processed_at < current_record.created_at:
            raise ValueError(
                "処理日時は作成日時以後である必要があります。"
            )

        try:
            with sqlite3.connect(
                self.database_path,
            ) as connection:
                cursor = connection.execute(
                    """
                    UPDATE trade_signals
                    SET
                        status = ?,
                        processed_at = ?,
                        process_note = ?,
                        updated_at = ?
                    WHERE signal_id = ?
                      AND status = ?
                    """,
                    (
                        target_status.value,
                        processed_at.isoformat(),
                        normalized_process_note,
                        processed_at.isoformat(),
                        normalized_signal_id,
                        SignalStatus.PENDING.value,
                    ),
                )

                connection.commit()

                if cursor.rowcount != 1:
                    raise SignalStateTransitionError(
                        "売買シグナルの状態を"
                        "更新できませんでした。 "
                        f"signal_id={normalized_signal_id}"
                    )

        except SignalStateTransitionError:
            raise

        except sqlite3.Error as error:
            raise SignalRepositoryError(
                "売買シグナルの状態を"
                "更新できませんでした。 "
                f"signal_id={normalized_signal_id}"
            ) from error

        return self.get(
            normalized_signal_id,
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
            timezone.utc,
        )

    @staticmethod
    def _serialize_metadata(
        metadata: dict[str, Any],
    ) -> str:
        """メタデータをJSON文字列へ変換する。"""

        try:
            return json.dumps(
                metadata,
                ensure_ascii=False,
                sort_keys=True,
                separators=(
                    ",",
                    ":",
                ),
            )

        except (
            TypeError,
            ValueError,
        ) as error:
            raise ValueError(
                "シグナルのメタデータを"
                "JSONへ変換できません。"
            ) from error

    @staticmethod
    def _deserialize_metadata(
        raw_metadata: object,
    ) -> dict[str, Any]:
        """JSON文字列からメタデータを復元する。"""

        try:
            parsed = json.loads(
                str(raw_metadata),
            )

        except json.JSONDecodeError as error:
            raise SignalRepositoryError(
                "保存済みシグナルのメタデータが"
                "不正なJSONです。"
            ) from error

        if not isinstance(
            parsed,
            dict,
        ):
            raise SignalRepositoryError(
                "保存済みシグナルのメタデータは"
                "辞書形式である必要があります。"
            )

        return parsed

    @staticmethod
    def _normalize_signal_id(
        signal_id: str,
    ) -> str:
        """シグナルIDを検証して正規化する。"""

        normalized_signal_id = signal_id.strip()

        if not normalized_signal_id:
            raise ValueError(
                "シグナルIDを指定してください。"
            )

        return normalized_signal_id

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
                "銘柄コードは4桁または5桁で指定してください。"
            )

        return normalized_code

    @staticmethod
    def _normalize_strategy_name(
        strategy_name: str,
    ) -> str:
        """戦略名を検証して正規化する。"""

        normalized_strategy_name = (
            strategy_name.strip()
        )

        if not normalized_strategy_name:
            raise ValueError(
                "戦略名を指定してください。"
            )

        return normalized_strategy_name

    @staticmethod
    def _select_sql() -> str:
        """シグナル取得用SELECT文を返す。"""

        return """
            SELECT
                id,
                signal_id,
                code,
                strategy_name,
                action,
                generated_at,
                signal_price,
                quantity,
                reason,
                confidence,
                metadata_json,
                status,
                processed_at,
                process_note,
                created_at,
                updated_at
            FROM trade_signals
        """

    @classmethod
    def _row_to_record(
        cls,
        row: tuple[object, ...],
    ) -> TradeSignalRecord:
        """SQLiteの1行を保存済みシグナルへ変換する。"""

        signal = TradeSignal(
            signal_id=str(row[1]),
            code=str(row[2]),
            strategy_name=str(row[3]),
            action=SignalAction(
                str(row[4]),
            ),
            generated_at=datetime.fromisoformat(
                str(row[5]),
            ),
            signal_price=float(row[6]),
            quantity=int(row[7]),
            reason=str(row[8]),
            confidence=(
                float(row[9])
                if row[9] is not None
                else None
            ),
            metadata=cls._deserialize_metadata(
                row[10],
            ),
        )

        processed_at = (
            datetime.fromisoformat(
                str(row[12]),
            )
            if row[12] is not None
            else None
        )

        process_note = (
            str(row[13])
            if row[13] is not None
            else None
        )

        return cls._create_record(
            record_id=int(row[0]),
            signal=signal,
            status=SignalStatus(
                str(row[11]),
            ),
            processed_at=processed_at,
            process_note=process_note,
            created_at=datetime.fromisoformat(
                str(row[14]),
            ),
            updated_at=datetime.fromisoformat(
                str(row[15]),
            ),
        )

    @staticmethod
    def _create_record(
        *,
        record_id: int,
        signal: TradeSignal,
        status: SignalStatus,
        processed_at: datetime | None,
        process_note: str | None,
        created_at: datetime,
        updated_at: datetime,
    ) -> TradeSignalRecord:
        """保存済みシグナルを作成する。"""

        return TradeSignalRecord(
            id=record_id,
            signal=signal,
            status=status,
            processed_at=processed_at,
            process_note=process_note,
            created_at=created_at,
            updated_at=updated_at,
        )