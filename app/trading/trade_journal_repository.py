"""Trade JournalをSQLiteへ永続化する。"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Iterable
from datetime import datetime, timezone
from pathlib import Path

from app.trading.trade_journal_models import (
    TradeJournalEntry,
    TradeJournalRecord,
)


class TradeJournalRepositoryError(RuntimeError):
    """Trade Journal Repositoryの基底例外。"""


class TradeJournalNotFoundError(
    TradeJournalRepositoryError
):
    """指定したTrade Journalが存在しないことを表す。"""


class TradeJournalRepository:
    """完了トレードをUpsert可能な形で管理する。"""

    def __init__(
        self,
        database_path: Path,
        *,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self.database_path = Path(database_path)
        self.now_provider = (
            now_provider
            if now_provider is not None
            else lambda: datetime.now(timezone.utc)
        )

    def save(
        self,
        entry: TradeJournalEntry,
    ) -> TradeJournalRecord:
        now = self._current_time()

        try:
            metadata_json = json.dumps(
                entry.metadata,
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
                connection.execute(
                    """
                    INSERT INTO trade_journal (
                        trade_id,
                        strategy_name,
                        code,
                        entry_signal_id,
                        exit_signal_id,
                        entry_execution_id,
                        exit_execution_id,
                        entry_at,
                        exit_at,
                        entry_price,
                        exit_price,
                        quantity,
                        entry_cost,
                        exit_cost,
                        realized_profit_loss,
                        return_rate,
                        holding_minutes,
                        exit_reason,
                        maximum_favorable_excursion,
                        maximum_adverse_excursion,
                        maximum_favorable_excursion_rate,
                        maximum_adverse_excursion_rate,
                        metadata_json,
                        created_at,
                        updated_at
                    )
                    VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                    )
                    ON CONFLICT(trade_id) DO UPDATE SET
                        strategy_name = excluded.strategy_name,
                        code = excluded.code,
                        entry_signal_id = excluded.entry_signal_id,
                        exit_signal_id = excluded.exit_signal_id,
                        entry_execution_id = excluded.entry_execution_id,
                        exit_execution_id = excluded.exit_execution_id,
                        entry_at = excluded.entry_at,
                        exit_at = excluded.exit_at,
                        entry_price = excluded.entry_price,
                        exit_price = excluded.exit_price,
                        quantity = excluded.quantity,
                        entry_cost = excluded.entry_cost,
                        exit_cost = excluded.exit_cost,
                        realized_profit_loss =
                            excluded.realized_profit_loss,
                        return_rate = excluded.return_rate,
                        holding_minutes = excluded.holding_minutes,
                        exit_reason = excluded.exit_reason,
                        maximum_favorable_excursion =
                            excluded.maximum_favorable_excursion,
                        maximum_adverse_excursion =
                            excluded.maximum_adverse_excursion,
                        maximum_favorable_excursion_rate =
                            excluded.maximum_favorable_excursion_rate,
                        maximum_adverse_excursion_rate =
                            excluded.maximum_adverse_excursion_rate,
                        metadata_json = excluded.metadata_json,
                        updated_at = excluded.updated_at
                    """,
                    (
                        entry.trade_id,
                        entry.strategy_name,
                        entry.code,
                        entry.entry_signal_id,
                        entry.exit_signal_id,
                        entry.entry_execution_id,
                        entry.exit_execution_id,
                        entry.entry_at.astimezone(
                            timezone.utc
                        ).isoformat(),
                        entry.exit_at.astimezone(
                            timezone.utc
                        ).isoformat(),
                        entry.entry_price,
                        entry.exit_price,
                        entry.quantity,
                        entry.entry_cost,
                        entry.exit_cost,
                        entry.realized_profit_loss,
                        entry.return_rate,
                        entry.holding_minutes,
                        entry.exit_reason,
                        entry.maximum_favorable_excursion,
                        entry.maximum_adverse_excursion,
                        entry.maximum_favorable_excursion_rate,
                        entry.maximum_adverse_excursion_rate,
                        metadata_json,
                        now.isoformat(),
                        now.isoformat(),
                    ),
                )
                connection.commit()

                row = connection.execute(
                    self._select_sql()
                    + """
                    WHERE trade_id = ?
                    """,
                    (entry.trade_id,),
                ).fetchone()
        except sqlite3.Error as error:
            raise TradeJournalRepositoryError(
                "Trade Journalを保存できませんでした。 "
                f"trade_id={entry.trade_id}"
            ) from error

        assert row is not None
        return self._row_to_record(row)

    def save_all(
        self,
        entries: Iterable[TradeJournalEntry],
    ) -> int:
        materialized = tuple(entries)

        for entry in materialized:
            self.save(entry)

        return len(materialized)

    def get(
        self,
        trade_id: str,
    ) -> TradeJournalRecord:
        normalized = trade_id.strip()

        if not normalized:
            raise ValueError(
                "Trade IDを指定してください。"
            )

        try:
            with self._connect() as connection:
                row = connection.execute(
                    self._select_sql()
                    + """
                    WHERE trade_id = ?
                    """,
                    (normalized,),
                ).fetchone()
        except sqlite3.Error as error:
            raise TradeJournalRepositoryError(
                "Trade Journalを読み込めませんでした。 "
                f"trade_id={normalized}"
            ) from error

        if row is None:
            raise TradeJournalNotFoundError(
                "指定されたTrade Journalが存在しません。 "
                f"trade_id={normalized}"
            )

        return self._row_to_record(row)

    def list_recent(
        self,
        *,
        limit: int = 100,
        strategy_name: str | None = None,
        code: str | None = None,
    ) -> tuple[TradeJournalRecord, ...]:
        if limit <= 0:
            raise ValueError(
                "取得件数は0より大きい必要があります。"
            )

        conditions: list[str] = []
        parameters: list[object] = []

        if strategy_name is not None:
            normalized_strategy = strategy_name.strip()

            if not normalized_strategy:
                raise ValueError(
                    "戦略名を指定してください。"
                )

            conditions.append(
                "strategy_name = ?"
            )
            parameters.append(
                normalized_strategy
            )

        if code is not None:
            normalized_code = code.strip()

            if not normalized_code:
                raise ValueError(
                    "銘柄コードを指定してください。"
                )

            conditions.append("code = ?")
            parameters.append(normalized_code)

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
                    ORDER BY exit_at DESC, id DESC
                    LIMIT ?
                    """,
                    parameters,
                ).fetchall()
        except sqlite3.Error as error:
            raise TradeJournalRepositoryError(
                "Trade Journal一覧を読み込めませんでした。"
            ) from error

        return tuple(
            self._row_to_record(row)
            for row in rows
        )

    def count(
        self,
        *,
        strategy_name: str | None = None,
        code: str | None = None,
    ) -> int:
        conditions: list[str] = []
        parameters: list[object] = []

        if strategy_name is not None:
            conditions.append("strategy_name = ?")
            parameters.append(strategy_name.strip())

        if code is not None:
            conditions.append("code = ?")
            parameters.append(code.strip())

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
                    FROM trade_journal
                    {where_clause}
                    """,
                    parameters,
                ).fetchone()
        except sqlite3.Error as error:
            raise TradeJournalRepositoryError(
                "Trade Journal件数を取得できませんでした。"
            ) from error

        return int(row[0]) if row is not None else 0

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.database_path
        )
        connection.execute(
            "PRAGMA foreign_keys = ON"
        )
        return connection

    def _current_time(self) -> datetime:
        value = self.now_provider()

        if value.tzinfo is None:
            raise ValueError(
                "現在日時にはタイムゾーンが必要です。"
            )

        return value.astimezone(timezone.utc)

    @staticmethod
    def _select_sql() -> str:
        return """
            SELECT
                id,
                trade_id,
                strategy_name,
                code,
                entry_signal_id,
                exit_signal_id,
                entry_execution_id,
                exit_execution_id,
                entry_at,
                exit_at,
                entry_price,
                exit_price,
                quantity,
                entry_cost,
                exit_cost,
                realized_profit_loss,
                return_rate,
                holding_minutes,
                exit_reason,
                maximum_favorable_excursion,
                maximum_adverse_excursion,
                maximum_favorable_excursion_rate,
                maximum_adverse_excursion_rate,
                metadata_json,
                created_at,
                updated_at
            FROM trade_journal
        """

    @classmethod
    def _row_to_record(
        cls,
        row: tuple[object, ...],
    ) -> TradeJournalRecord:
        try:
            metadata = json.loads(str(row[23]))
        except (
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ) as error:
            raise TradeJournalRepositoryError(
                "保存済みメタデータを読み込めませんでした。"
            ) from error

        return TradeJournalRecord(
            id=int(row[0]),
            entry=TradeJournalEntry(
                trade_id=str(row[1]),
                strategy_name=str(row[2]),
                code=str(row[3]),
                entry_signal_id=str(row[4]),
                exit_signal_id=str(row[5]),
                entry_execution_id=str(row[6]),
                exit_execution_id=str(row[7]),
                entry_at=cls._parse_datetime(str(row[8])),
                exit_at=cls._parse_datetime(str(row[9])),
                entry_price=float(row[10]),
                exit_price=float(row[11]),
                quantity=int(row[12]),
                entry_cost=float(row[13]),
                exit_cost=float(row[14]),
                realized_profit_loss=float(row[15]),
                return_rate=float(row[16]),
                holding_minutes=float(row[17]),
                exit_reason=(
                    str(row[18])
                    if row[18] is not None
                    else None
                ),
                maximum_favorable_excursion=(
                    float(row[19])
                    if row[19] is not None
                    else None
                ),
                maximum_adverse_excursion=(
                    float(row[20])
                    if row[20] is not None
                    else None
                ),
                maximum_favorable_excursion_rate=(
                    float(row[21])
                    if row[21] is not None
                    else None
                ),
                maximum_adverse_excursion_rate=(
                    float(row[22])
                    if row[22] is not None
                    else None
                ),
                metadata=metadata,
            ),
            created_at=cls._parse_datetime(
                str(row[24])
            ),
            updated_at=cls._parse_datetime(
                str(row[25])
            ),
        )

    @staticmethod
    def _parse_datetime(
        value: str,
    ) -> datetime:
        parsed = datetime.fromisoformat(value)

        if parsed.tzinfo is None:
            parsed = parsed.replace(
                tzinfo=timezone.utc
            )

        return parsed.astimezone(timezone.utc)
