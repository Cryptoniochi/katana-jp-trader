"""新高値ブレイク候補をSQLiteへ保存・取得する。"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Iterable
from datetime import date, datetime, timezone
from pathlib import Path

from app.strategy.high_breakout_models import (
    HighBreakoutCandidate,
    HighBreakoutType,
)


class HighBreakoutCandidateRepositoryError(RuntimeError):
    """新高値候補Repositoryの基底例外。"""


class HighBreakoutCandidateNotFoundError(
    HighBreakoutCandidateRepositoryError
):
    """指定された新高値候補が存在しないことを表す。"""


class HighBreakoutCandidateRepository:
    """新高値ブレイク候補を営業日・銘柄単位で管理する。"""

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
        candidate: HighBreakoutCandidate,
    ) -> HighBreakoutCandidate:
        """候補を営業日・銘柄単位でUpsertする。"""

        now = self._current_time()
        breakout_types_json = json.dumps(
            [
                item.value
                for item in candidate.breakout_types
            ],
            ensure_ascii=False,
            separators=(",", ":"),
        )

        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO high_breakout_candidates (
                        code,
                        trading_date,
                        breakout_types_json,
                        close_price,
                        previous_20_day_high,
                        previous_60_day_high,
                        previous_year_high,
                        volume_ratio,
                        turnover,
                        atr,
                        atr_rate,
                        score,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(code, trading_date) DO UPDATE SET
                        breakout_types_json =
                            excluded.breakout_types_json,
                        close_price = excluded.close_price,
                        previous_20_day_high =
                            excluded.previous_20_day_high,
                        previous_60_day_high =
                            excluded.previous_60_day_high,
                        previous_year_high =
                            excluded.previous_year_high,
                        volume_ratio = excluded.volume_ratio,
                        turnover = excluded.turnover,
                        atr = excluded.atr,
                        atr_rate = excluded.atr_rate,
                        score = excluded.score,
                        updated_at = excluded.updated_at
                    """,
                    (
                        candidate.code,
                        candidate.trading_date.isoformat(),
                        breakout_types_json,
                        candidate.close_price,
                        candidate.previous_20_day_high,
                        candidate.previous_60_day_high,
                        candidate.previous_year_high,
                        candidate.volume_ratio,
                        candidate.turnover,
                        candidate.atr,
                        candidate.atr_rate,
                        candidate.score,
                        now.isoformat(),
                        now.isoformat(),
                    ),
                )
                connection.commit()

        except sqlite3.Error as error:
            raise HighBreakoutCandidateRepositoryError(
                "新高値候補を保存できませんでした。 "
                f"code={candidate.code} "
                f"trading_date={candidate.trading_date}"
            ) from error

        return candidate

    def save_all(
        self,
        candidates: Iterable[HighBreakoutCandidate],
    ) -> int:
        """複数候補を保存して件数を返す。"""

        materialized = tuple(candidates)

        for candidate in materialized:
            self.save(candidate)

        return len(materialized)

    def get(
        self,
        *,
        code: str,
        trading_date: date,
    ) -> HighBreakoutCandidate:
        """銘柄・営業日に一致する候補を返す。"""

        normalized_code = self._normalize_code(code)

        try:
            with self._connect() as connection:
                row = connection.execute(
                    self._select_sql()
                    + """
                    WHERE code = ?
                      AND trading_date = ?
                    """,
                    (
                        normalized_code,
                        trading_date.isoformat(),
                    ),
                ).fetchone()

        except sqlite3.Error as error:
            raise HighBreakoutCandidateRepositoryError(
                "新高値候補を読み込めませんでした。 "
                f"code={normalized_code} "
                f"trading_date={trading_date}"
            ) from error

        if row is None:
            raise HighBreakoutCandidateNotFoundError(
                "指定された新高値候補が存在しません。 "
                f"code={normalized_code} "
                f"trading_date={trading_date}"
            )

        return self._row_to_candidate(row)

    def list_by_date(
        self,
        trading_date: date,
        *,
        limit: int = 100,
    ) -> tuple[HighBreakoutCandidate, ...]:
        """指定営業日の候補をスコア順で返す。"""

        if limit <= 0:
            raise ValueError(
                "取得件数は0より大きい必要があります。"
            )

        try:
            with self._connect() as connection:
                rows = connection.execute(
                    self._select_sql()
                    + """
                    WHERE trading_date = ?
                    ORDER BY score DESC, code ASC
                    LIMIT ?
                    """,
                    (
                        trading_date.isoformat(),
                        limit,
                    ),
                ).fetchall()

        except sqlite3.Error as error:
            raise HighBreakoutCandidateRepositoryError(
                "新高値候補一覧を読み込めませんでした。 "
                f"trading_date={trading_date}"
            ) from error

        return tuple(
            self._row_to_candidate(row)
            for row in rows
        )

    def list_recent(
        self,
        *,
        limit: int = 100,
        code: str | None = None,
    ) -> tuple[HighBreakoutCandidate, ...]:
        """候補を営業日の新しい順で返す。"""

        if limit <= 0:
            raise ValueError(
                "取得件数は0より大きい必要があります。"
            )

        conditions: list[str] = []
        parameters: list[object] = []

        if code is not None:
            conditions.append("code = ?")
            parameters.append(
                self._normalize_code(code)
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
                    ORDER BY
                        trading_date DESC,
                        score DESC,
                        code ASC
                    LIMIT ?
                    """,
                    parameters,
                ).fetchall()

        except sqlite3.Error as error:
            raise HighBreakoutCandidateRepositoryError(
                "新高値候補履歴を読み込めませんでした。"
            ) from error

        return tuple(
            self._row_to_candidate(row)
            for row in rows
        )

    def delete_date(
        self,
        trading_date: date,
    ) -> int:
        """指定営業日の候補をすべて削除する。"""

        try:
            with self._connect() as connection:
                cursor = connection.execute(
                    """
                    DELETE FROM high_breakout_candidates
                    WHERE trading_date = ?
                    """,
                    (
                        trading_date.isoformat(),
                    ),
                )
                connection.commit()
                return int(cursor.rowcount)

        except sqlite3.Error as error:
            raise HighBreakoutCandidateRepositoryError(
                "新高値候補を削除できませんでした。 "
                f"trading_date={trading_date}"
            ) from error

    def count(
        self,
        *,
        trading_date: date | None = None,
        code: str | None = None,
    ) -> int:
        """条件に一致する候補件数を返す。"""

        conditions: list[str] = []
        parameters: list[object] = []

        if trading_date is not None:
            conditions.append("trading_date = ?")
            parameters.append(
                trading_date.isoformat()
            )

        if code is not None:
            conditions.append("code = ?")
            parameters.append(
                self._normalize_code(code)
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
                    FROM high_breakout_candidates
                    {where_clause}
                    """,
                    parameters,
                ).fetchone()

        except sqlite3.Error as error:
            raise HighBreakoutCandidateRepositoryError(
                "新高値候補件数を取得できませんでした。"
            ) from error

        return int(row[0]) if row is not None else 0

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(
            self.database_path
        )

    def _current_time(self) -> datetime:
        current = self.now_provider()

        if current.tzinfo is None:
            raise ValueError(
                "現在日時にはタイムゾーンが必要です。"
            )

        return current.astimezone(
            timezone.utc
        )

    @staticmethod
    def _normalize_code(
        code: str,
    ) -> str:
        normalized = code.strip()

        if not normalized:
            raise ValueError(
                "銘柄コードを指定してください。"
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
        return """
            SELECT
                code,
                trading_date,
                breakout_types_json,
                close_price,
                previous_20_day_high,
                previous_60_day_high,
                previous_year_high,
                volume_ratio,
                turnover,
                atr,
                atr_rate,
                score
            FROM high_breakout_candidates
        """

    @staticmethod
    def _row_to_candidate(
        row: tuple[object, ...],
    ) -> HighBreakoutCandidate:
        try:
            raw_types = json.loads(
                str(row[2])
            )
        except (
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ) as error:
            raise HighBreakoutCandidateRepositoryError(
                "保存済みブレイク種別を"
                "読み込めませんでした。"
            ) from error

        if not isinstance(raw_types, list):
            raise HighBreakoutCandidateRepositoryError(
                "保存済みブレイク種別は"
                "配列である必要があります。"
            )

        return HighBreakoutCandidate(
            code=str(row[0]),
            trading_date=date.fromisoformat(
                str(row[1])
            ),
            breakout_types=tuple(
                HighBreakoutType(str(value))
                for value in raw_types
            ),
            close_price=float(row[3]),
            previous_20_day_high=(
                float(row[4])
                if row[4] is not None
                else None
            ),
            previous_60_day_high=(
                float(row[5])
                if row[5] is not None
                else None
            ),
            previous_year_high=(
                float(row[6])
                if row[6] is not None
                else None
            ),
            volume_ratio=float(row[7]),
            turnover=float(row[8]),
            atr=float(row[9]),
            atr_rate=float(row[10]),
            score=float(row[11]),
        )
