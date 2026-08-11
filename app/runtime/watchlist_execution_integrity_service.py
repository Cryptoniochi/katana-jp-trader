"""Dynamic WatchlistからPaper Trading約定までの整合性を監査する。"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True, slots=True)
class WatchlistExecutionSymbolAudit:
    """1銘柄分のWatchlist-to-Execution監査結果。"""

    code: str
    selected: bool
    loaded: bool
    monitored: bool
    signal_count: int
    execution_count: int

    @property
    def status(self) -> str:
        if not self.selected:
            return "not_selected"
        if not self.loaded:
            return "not_loaded"
        if not self.monitored:
            return "not_monitored"
        if self.execution_count > 0:
            return "executed"
        if self.signal_count > 0:
            return "signaled_no_execution"
        return "monitored_no_signal"

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "selected": self.selected,
            "loaded": self.loaded,
            "monitored": self.monitored,
            "signal_count": self.signal_count,
            "execution_count": self.execution_count,
            "status": self.status,
        }


@dataclass(frozen=True, slots=True)
class WatchlistExecutionIntegrityResult:
    """日次Watchlist-to-Execution監査結果。"""

    generated_at: datetime
    trading_date: date
    selected_codes: tuple[str, ...]
    loaded_codes: tuple[str, ...]
    monitored_codes: tuple[str, ...]
    signal_codes: tuple[str, ...]
    execution_codes: tuple[str, ...]
    orphan_signal_codes: tuple[str, ...]
    orphan_execution_codes: tuple[str, ...]
    selected_not_loaded_codes: tuple[str, ...]
    loaded_not_monitored_codes: tuple[str, ...]
    monitored_not_loaded_codes: tuple[str, ...]
    symbol_audits: tuple[WatchlistExecutionSymbolAudit, ...]
    integrity_ok: bool
    trace_available: bool

    @property
    def selected_count(self) -> int:
        return len(self.selected_codes)

    @property
    def loaded_count(self) -> int:
        return len(self.loaded_codes)

    @property
    def monitored_count(self) -> int:
        return len(self.monitored_codes)

    @property
    def signal_count(self) -> int:
        return sum(item.signal_count for item in self.symbol_audits)

    @property
    def execution_count(self) -> int:
        return sum(
            item.execution_count
            for item in self.symbol_audits
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "generated_at": self.generated_at.isoformat(),
            "trading_date": self.trading_date.isoformat(),
            "integrity_ok": self.integrity_ok,
            "trace_available": self.trace_available,
            "selected_count": self.selected_count,
            "loaded_count": self.loaded_count,
            "monitored_count": self.monitored_count,
            "signal_count": self.signal_count,
            "execution_count": self.execution_count,
            "selected_codes": list(self.selected_codes),
            "loaded_codes": list(self.loaded_codes),
            "monitored_codes": list(self.monitored_codes),
            "signal_codes": list(self.signal_codes),
            "execution_codes": list(self.execution_codes),
            "selected_not_loaded_codes": list(
                self.selected_not_loaded_codes
            ),
            "loaded_not_monitored_codes": list(
                self.loaded_not_monitored_codes
            ),
            "monitored_not_loaded_codes": list(
                self.monitored_not_loaded_codes
            ),
            "orphan_signal_codes": list(
                self.orphan_signal_codes
            ),
            "orphan_execution_codes": list(
                self.orphan_execution_codes
            ),
            "symbols": [
                item.to_dict()
                for item in self.symbol_audits
            ],
        }


class WatchlistExecutionIntegrityService:
    """選定・読込・監視・Signal・Executionのコード集合を突合する。"""

    def __init__(
        self,
        *,
        database_path: Path,
        watchlist_path: Path = Path("watchlist.txt"),
        explainability_path: Path = Path(
            "reports/watchlist/explainability/latest.json"
        ),
        trace_path: Path = Path(
            "logs/risk/paper_trading_trace.jsonl"
        ),
    ) -> None:
        self.database_path = Path(database_path)
        self.watchlist_path = Path(watchlist_path)
        self.explainability_path = Path(explainability_path)
        self.trace_path = Path(trace_path)

    def audit(
        self,
        *,
        trading_date: date,
    ) -> WatchlistExecutionIntegrityResult:
        selected_codes = self._load_selected_codes(
            trading_date=trading_date
        )
        loaded_codes = self._load_watchlist_codes()
        (
            monitored_codes,
            trace_signal_counts,
            trace_execution_counts,
            trace_available,
        ) = self._load_trace(
            trading_date=trading_date
        )

        db_signal_counts = self._load_database_code_counts(
            table_name="trade_signals",
            trading_date=trading_date,
        )
        db_execution_counts = self._load_database_code_counts(
            table_name="trade_executions",
            trading_date=trading_date,
        )

        signal_counts = self._merge_counts(
            trace_signal_counts,
            db_signal_counts,
        )
        execution_counts = self._merge_counts(
            trace_execution_counts,
            db_execution_counts,
        )

        selected_set = set(selected_codes)
        loaded_set = set(loaded_codes)
        monitored_set = set(monitored_codes)
        signal_set = set(signal_counts)
        execution_set = set(execution_counts)

        # Traceが存在しない過去日でも、loadedまでは監査可能。
        if not trace_available:
            monitored_set = set()
            monitored_codes = ()

        selected_not_loaded = tuple(
            sorted(selected_set - loaded_set)
        )
        loaded_not_monitored = tuple(
            sorted(
                loaded_set - monitored_set
            )
        ) if trace_available else ()
        monitored_not_loaded = tuple(
            sorted(
                monitored_set - loaded_set
            )
        ) if trace_available else ()

        orphan_signal = tuple(
            sorted(signal_set - loaded_set)
        )
        orphan_execution = tuple(
            sorted(execution_set - signal_set)
        )

        all_codes = sorted(
            selected_set
            | loaded_set
            | monitored_set
            | signal_set
            | execution_set
        )
        audits = tuple(
            WatchlistExecutionSymbolAudit(
                code=code,
                selected=code in selected_set,
                loaded=code in loaded_set,
                monitored=code in monitored_set,
                signal_count=signal_counts.get(code, 0),
                execution_count=execution_counts.get(
                    code,
                    0,
                ),
            )
            for code in all_codes
        )

        integrity_ok = (
            not selected_not_loaded
            and not orphan_signal
            and not orphan_execution
            and (
                not trace_available
                or (
                    not loaded_not_monitored
                    and not monitored_not_loaded
                )
            )
        )

        return WatchlistExecutionIntegrityResult(
            generated_at=datetime.now(timezone.utc),
            trading_date=trading_date,
            selected_codes=selected_codes,
            loaded_codes=loaded_codes,
            monitored_codes=tuple(
                sorted(monitored_set)
            ),
            signal_codes=tuple(
                sorted(signal_set)
            ),
            execution_codes=tuple(
                sorted(execution_set)
            ),
            orphan_signal_codes=orphan_signal,
            orphan_execution_codes=orphan_execution,
            selected_not_loaded_codes=(
                selected_not_loaded
            ),
            loaded_not_monitored_codes=(
                loaded_not_monitored
            ),
            monitored_not_loaded_codes=(
                monitored_not_loaded
            ),
            symbol_audits=audits,
            integrity_ok=integrity_ok,
            trace_available=trace_available,
        )

    def _load_selected_codes(
        self,
        *,
        trading_date: date,
    ) -> tuple[str, ...]:
        if not self.explainability_path.exists():
            return ()

        try:
            payload = json.loads(
                self.explainability_path.read_text(
                    encoding="utf-8"
                )
            )
        except (
            OSError,
            UnicodeError,
            json.JSONDecodeError,
        ):
            return ()

        if not isinstance(payload, dict):
            return ()

        target_date = str(
            payload.get("target_date") or ""
        )
        if target_date != trading_date.isoformat():
            return ()

        candidates = payload.get("candidates")
        if not isinstance(candidates, list):
            return ()

        codes: list[str] = []
        for item in candidates:
            if not isinstance(item, dict):
                continue
            if not bool(item.get("selected")):
                continue
            code = self._normalize_code(
                item.get("code")
            )
            if code and code not in codes:
                codes.append(code)
        return tuple(codes)

    def _load_watchlist_codes(
        self,
    ) -> tuple[str, ...]:
        if not self.watchlist_path.exists():
            return ()

        codes: list[str] = []
        for raw in self.watchlist_path.read_text(
            encoding="utf-8"
        ).splitlines():
            code = self._normalize_code(raw)
            if code and code not in codes:
                codes.append(code)
        return tuple(codes)

    def _load_trace(
        self,
        *,
        trading_date: date,
    ) -> tuple[
        tuple[str, ...],
        dict[str, int],
        dict[str, int],
        bool,
    ]:
        """指定営業日の最新Runtime sessionだけを読み込む。

        同日にPaper Tradingを再起動した場合、古いruntime_startedの
        codesを混ぜると「現在は監視していない銘柄」までmonitored扱いに
        なってしまうため、最後のruntime_started以降だけを監査対象にする。
        """

        if not self.trace_path.exists():
            return (), {}, {}, False

        try:
            lines = self.trace_path.read_text(
                encoding="utf-8"
            ).splitlines()
        except (OSError, UnicodeError):
            return (), {}, {}, False

        from zoneinfo import ZoneInfo
        tokyo = ZoneInfo("Asia/Tokyo")
        events: list[tuple[datetime, dict[str, Any]]] = []

        for line in lines:
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue

            occurred_at = self._parse_datetime(
                event.get("occurred_at")
            )
            if occurred_at is None:
                continue
            if occurred_at.astimezone(tokyo).date() != trading_date:
                continue

            events.append((occurred_at, event))

        if not events:
            return (), {}, {}, False

        events.sort(key=lambda item: item[0])

        latest_start_index: int | None = None
        monitored: set[str] = set()

        for index, (_occurred_at, event) in enumerate(events):
            if str(event.get("event_type") or "") != "runtime_started":
                continue

            latest_start_index = index
            monitored = set()
            payload = event.get("payload")
            if not isinstance(payload, dict):
                payload = {}
            raw_codes = payload.get("codes")
            if isinstance(raw_codes, list):
                for raw_code in raw_codes:
                    normalized = self._normalize_code(
                        raw_code
                    )
                    if normalized:
                        monitored.add(normalized)

        if latest_start_index is None:
            return (), {}, {}, False

        signals: dict[str, int] = {}
        executions: dict[str, int] = {}

        for _occurred_at, event in events[latest_start_index:]:
            event_type = str(
                event.get("event_type") or ""
            )
            code = self._normalize_code(
                event.get("code")
            )

            if (
                event_type == "signal_generated"
                and code
            ):
                signals[code] = signals.get(code, 0) + 1

            if (
                event_type in {
                    "broker_executed",
                    "execution_saved",
                }
                and code
            ):
                executions[code] = (
                    executions.get(code, 0) + 1
                )

        return (
            tuple(sorted(monitored)),
            signals,
            executions,
            True,
        )

    def _load_database_code_counts(
        self,
        *,
        table_name: str,
        trading_date: date,
    ) -> dict[str, int]:
        if not self.database_path.exists():
            return {}

        with sqlite3.connect(
            self.database_path
        ) as connection:
            connection.row_factory = sqlite3.Row
            if not self._table_exists(
                connection,
                table_name,
            ):
                return {}

            columns = {
                str(row["name"])
                for row in connection.execute(
                    f"PRAGMA table_info({table_name})"
                ).fetchall()
            }
            if "code" not in columns:
                return {}

            timestamp_column = self._resolve_timestamp_column(
                table_name=table_name,
                columns=columns,
            )
            if timestamp_column is None:
                return {}

            rows = connection.execute(
                f"""
                SELECT
                    code,
                    {timestamp_column}
                FROM {table_name}
                WHERE code IS NOT NULL
                """
            ).fetchall()

        counts: dict[str, int] = {}
        from zoneinfo import ZoneInfo
        tokyo = ZoneInfo("Asia/Tokyo")

        for row in rows:
            code = self._normalize_code(row["code"])
            if not code:
                continue
            occurred_at = self._parse_datetime(
                row[timestamp_column]
            )
            if occurred_at is None:
                continue
            if occurred_at.astimezone(tokyo).date() != trading_date:
                continue
            counts[code] = counts.get(code, 0) + 1

        return counts

    @staticmethod
    def _table_exists(
        connection: sqlite3.Connection,
        table_name: str,
    ) -> bool:
        row = connection.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type = 'table'
              AND name = ?
            """,
            (table_name,),
        ).fetchone()
        return row is not None

    @staticmethod
    def _resolve_timestamp_column(
        *,
        table_name: str,
        columns: set[str],
    ) -> str | None:
        preferred = {
            "trade_signals": (
                "generated_at",
                "created_at",
                "saved_at",
            ),
            "trade_executions": (
                "executed_at",
                "created_at",
                "saved_at",
            ),
        }
        for name in preferred.get(
            table_name,
            (),
        ):
            if name in columns:
                return name
        return None

    @staticmethod
    def _merge_counts(
        first: dict[str, int],
        second: dict[str, int],
    ) -> dict[str, int]:
        # TraceとDBは同じイベントを表すことがあるため合算せず、
        # 銘柄ごとに多い方を採用して二重カウントを避ける。
        keys = set(first) | set(second)
        return {
            key: max(
                first.get(key, 0),
                second.get(key, 0),
            )
            for key in keys
        }

    @staticmethod
    def _normalize_code(
        value: Any,
    ) -> str | None:
        text = str(value or "").strip().upper()
        if not text:
            return None
        return text

    @staticmethod
    def _parse_datetime(
        value: Any,
    ) -> datetime | None:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(
                text.replace("Z", "+00:00")
            )
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(
                tzinfo=timezone.utc
            )
        return parsed
