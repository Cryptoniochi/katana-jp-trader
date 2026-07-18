"""Paper Trading日次サマリーをSQLiteへ永続化する。"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from app.runtime.paper_trading_daily_report import (
    paper_trading_daily_summary_to_dict,
)
from app.runtime.paper_trading_runtime_models import (
    PaperTradingDailySummary,
    PaperTradingRuntimeStatus,
)


@dataclass(frozen=True, slots=True)
class PaperTradingDailyRecord:
    """SQLiteへ保存されたPaper Trading日次レコード。"""

    trading_date: date
    status: PaperTradingRuntimeStatus
    started_at: datetime
    completed_at: datetime
    cycle_count: int
    successful_cycle_count: int
    failed_cycle_count: int
    signal_count: int
    execution_count: int
    initial_equity: float | None
    final_equity: float | None
    net_profit_loss: float | None
    return_rate: float | None
    error_message: str | None
    payload: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        """永続化レコードを検証する。"""

        for name, value in {
            "開始日時": self.started_at,
            "完了日時": self.completed_at,
            "作成日時": self.created_at,
            "更新日時": self.updated_at,
        }.items():
            if value.tzinfo is None:
                raise ValueError(
                    f"{name}にはタイムゾーンが必要です。"
                )

        for name, value in {
            "サイクル数": self.cycle_count,
            "成功サイクル数": self.successful_cycle_count,
            "失敗サイクル数": self.failed_cycle_count,
            "シグナル数": self.signal_count,
            "約定数": self.execution_count,
        }.items():
            if value < 0:
                raise ValueError(
                    f"{name}は0以上である必要があります。"
                )

        if (
            self.successful_cycle_count
            + self.failed_cycle_count
            != self.cycle_count
        ):
            raise ValueError(
                "成功・失敗サイクル数が総サイクル数と一致しません。"
            )


class PaperTradingDailySummaryRepository:
    """Paper Trading日次サマリーのSQLite Repository。"""

    def __init__(
        self,
        database_path: Path,
        *,
        now_provider,
    ) -> None:
        """Database Pathと時計を設定する。"""

        self.database_path = Path(database_path)
        self.now_provider = now_provider
        self.database_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        self._initialize_table()

    def save(
        self,
        summary: PaperTradingDailySummary,
    ) -> PaperTradingDailyRecord:
        """日次サマリーを営業日単位でUpsertする。"""

        now = self._current_time()
        payload = paper_trading_daily_summary_to_dict(
            summary
        )

        with sqlite3.connect(
            self.database_path
        ) as connection:
            connection.execute(
                """
                INSERT INTO paper_trading_daily_summaries (
                    trading_date,
                    status,
                    started_at,
                    completed_at,
                    cycle_count,
                    successful_cycle_count,
                    failed_cycle_count,
                    signal_count,
                    execution_count,
                    initial_equity,
                    final_equity,
                    net_profit_loss,
                    return_rate,
                    error_message,
                    payload_json,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(trading_date) DO UPDATE SET
                    status = excluded.status,
                    started_at = excluded.started_at,
                    completed_at = excluded.completed_at,
                    cycle_count = excluded.cycle_count,
                    successful_cycle_count = excluded.successful_cycle_count,
                    failed_cycle_count = excluded.failed_cycle_count,
                    signal_count = excluded.signal_count,
                    execution_count = excluded.execution_count,
                    initial_equity = excluded.initial_equity,
                    final_equity = excluded.final_equity,
                    net_profit_loss = excluded.net_profit_loss,
                    return_rate = excluded.return_rate,
                    error_message = excluded.error_message,
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                """,
                (
                    summary.trading_date.isoformat(),
                    summary.status.value,
                    summary.started_at.isoformat(),
                    summary.completed_at.isoformat(),
                    summary.cycle_count,
                    summary.successful_cycle_count,
                    summary.failed_cycle_count,
                    summary.signal_count,
                    summary.execution_count,
                    summary.initial_equity,
                    summary.final_equity,
                    summary.net_profit_loss,
                    summary.return_rate,
                    summary.error_message,
                    json.dumps(
                        payload,
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    now.isoformat(),
                    now.isoformat(),
                ),
            )
            connection.commit()

        record = self.get(summary.trading_date)

        if record is None:
            raise RuntimeError(
                "保存したPaper Trading日次サマリーを取得できません。"
            )

        return record

    def get(
        self,
        trading_date: date,
    ) -> PaperTradingDailyRecord | None:
        """指定営業日の保存レコードを返す。"""

        with sqlite3.connect(
            self.database_path
        ) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                """
                SELECT *
                FROM paper_trading_daily_summaries
                WHERE trading_date = ?
                """,
                (trading_date.isoformat(),),
            ).fetchone()

        if row is None:
            return None

        return self._record_from_row(row)

    def list_recent(
        self,
        *,
        limit: int = 30,
    ) -> tuple[PaperTradingDailyRecord, ...]:
        """新しい営業日順で日次レコードを返す。"""

        if limit <= 0:
            raise ValueError(
                "取得件数は0より大きい必要があります。"
            )

        with sqlite3.connect(
            self.database_path
        ) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                """
                SELECT *
                FROM paper_trading_daily_summaries
                ORDER BY trading_date DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return tuple(
            self._record_from_row(row)
            for row in rows
        )

    def count(self) -> int:
        """保存済み営業日数を返す。"""

        with sqlite3.connect(
            self.database_path
        ) as connection:
            row = connection.execute(
                """
                SELECT COUNT(*)
                FROM paper_trading_daily_summaries
                """
            ).fetchone()

        return int(row[0])

    def _initialize_table(self) -> None:
        """日次サマリーテーブルを作成する。"""

        with sqlite3.connect(
            self.database_path
        ) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS
                paper_trading_daily_summaries (
                    trading_date TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    completed_at TEXT NOT NULL,
                    cycle_count INTEGER NOT NULL,
                    successful_cycle_count INTEGER NOT NULL,
                    failed_cycle_count INTEGER NOT NULL,
                    signal_count INTEGER NOT NULL,
                    execution_count INTEGER NOT NULL,
                    initial_equity REAL,
                    final_equity REAL,
                    net_profit_loss REAL,
                    return_rate REAL,
                    error_message TEXT,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS
                idx_paper_trading_daily_status
                ON paper_trading_daily_summaries(status)
                """
            )
            connection.commit()

    @staticmethod
    def _record_from_row(
        row: sqlite3.Row,
    ) -> PaperTradingDailyRecord:
        """SQLite RowをDomain Recordへ変換する。"""

        return PaperTradingDailyRecord(
            trading_date=date.fromisoformat(
                row["trading_date"]
            ),
            status=PaperTradingRuntimeStatus(
                row["status"]
            ),
            started_at=datetime.fromisoformat(
                row["started_at"]
            ),
            completed_at=datetime.fromisoformat(
                row["completed_at"]
            ),
            cycle_count=int(row["cycle_count"]),
            successful_cycle_count=int(
                row["successful_cycle_count"]
            ),
            failed_cycle_count=int(
                row["failed_cycle_count"]
            ),
            signal_count=int(row["signal_count"]),
            execution_count=int(
                row["execution_count"]
            ),
            initial_equity=row["initial_equity"],
            final_equity=row["final_equity"],
            net_profit_loss=row["net_profit_loss"],
            return_rate=row["return_rate"],
            error_message=row["error_message"],
            payload=json.loads(row["payload_json"]),
            created_at=datetime.fromisoformat(
                row["created_at"]
            ),
            updated_at=datetime.fromisoformat(
                row["updated_at"]
            ),
        )

    def _current_time(self) -> datetime:
        """タイムゾーン付き現在日時を返す。"""

        current = self.now_provider()

        if current.tzinfo is None:
            raise ValueError(
                "現在日時にはタイムゾーンが必要です。"
            )

        return current
