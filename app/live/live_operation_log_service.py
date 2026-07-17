"""リアルタイム運用ログをJSON Linesで保存・集計する。"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path
from typing import Any

from app.live.live_operation_log_models import (
    LiveDailyOperationSummary,
    LiveLogEventType,
    LiveLogLevel,
    LiveOperationLogEntry,
)


class LiveOperationLogError(RuntimeError):
    """運用ログの読み書き失敗。"""


class LiveOperationLogService:
    """日付別JSONLログを追加保存し、日次集計を作成する。"""

    def __init__(
        self,
        *,
        log_directory: Path,
    ) -> None:
        """ログ保存先を設定する。"""

        self.log_directory = log_directory

    def append(
        self,
        entry: LiveOperationLogEntry,
    ) -> Path:
        """1件のログを日付別JSONLへ追記する。"""

        path = self.path_for_date(
            entry.occurred_at.date()
        )
        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        payload = self._serialize_entry(entry)

        try:
            with path.open(
                "a",
                encoding="utf-8",
                newline="\n",
            ) as file:
                file.write(
                    json.dumps(
                        payload,
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                    + "\n"
                )
        except OSError as error:
            raise LiveOperationLogError(
                "運用ログを保存できませんでした。 "
                f"path={path}"
            ) from error

        return path

    def append_all(
        self,
        entries: Iterable[LiveOperationLogEntry],
    ) -> tuple[Path, ...]:
        """複数ログを順番に保存し、対象パスを返す。"""

        paths: list[Path] = []

        for entry in entries:
            path = self.append(entry)

            if path not in paths:
                paths.append(path)

        return tuple(paths)

    def read_date(
        self,
        trading_date: date,
    ) -> tuple[LiveOperationLogEntry, ...]:
        """指定日のログを発生順に読み込む。"""

        path = self.path_for_date(trading_date)

        if not path.exists():
            return ()

        if not path.is_file():
            raise LiveOperationLogError(
                "運用ログのパスがファイルではありません。 "
                f"path={path}"
            )

        entries: list[LiveOperationLogEntry] = []

        try:
            with path.open(
                "r",
                encoding="utf-8",
            ) as file:
                for line_number, raw_line in enumerate(
                    file,
                    start=1,
                ):
                    line = raw_line.strip()

                    if not line:
                        continue

                    try:
                        payload = json.loads(line)
                        entries.append(
                            self._deserialize_entry(payload)
                        )
                    except (
                        json.JSONDecodeError,
                        KeyError,
                        TypeError,
                        ValueError,
                    ) as error:
                        raise LiveOperationLogError(
                            "運用ログの内容が不正です。 "
                            f"path={path} line={line_number}"
                        ) from error
        except OSError as error:
            raise LiveOperationLogError(
                "運用ログを読み込めませんでした。 "
                f"path={path}"
            ) from error

        return tuple(
            sorted(
                entries,
                key=lambda entry: entry.occurred_at,
            )
        )

    def create_daily_summary(
        self,
        trading_date: date,
    ) -> LiveDailyOperationSummary:
        """指定日の運用ログから集計を作成する。"""

        entries = self.read_date(trading_date)

        return LiveDailyOperationSummary(
            trading_date=trading_date,
            log_count=len(entries),
            cycle_started_count=self._count_event(
                entries,
                LiveLogEventType.CYCLE_STARTED,
            ),
            cycle_completed_count=self._count_event(
                entries,
                LiveLogEventType.CYCLE_COMPLETED,
            ),
            market_poll_count=self._count_event(
                entries,
                LiveLogEventType.MARKET_POLL,
            ),
            signal_count=self._count_event(
                entries,
                LiveLogEventType.SIGNAL,
            ),
            risk_rejected_count=sum(
                entry.event_type is LiveLogEventType.RISK
                and entry.metadata.get("decision")
                == "rejected"
                for entry in entries
            ),
            risk_halted_count=sum(
                entry.event_type is LiveLogEventType.RISK
                and entry.metadata.get("decision")
                == "halted"
                for entry in entries
            ),
            order_count=self._count_event(
                entries,
                LiveLogEventType.ORDER,
            ),
            execution_count=self._count_event(
                entries,
                LiveLogEventType.EXECUTION,
            ),
            error_count=sum(
                entry.level in {
                    LiveLogLevel.ERROR,
                    LiveLogLevel.CRITICAL,
                }
                for entry in entries
            ),
            critical_count=sum(
                entry.level is LiveLogLevel.CRITICAL
                for entry in entries
            ),
            codes=tuple(
                entry.code
                for entry in entries
                if entry.code is not None
            ),
        )

    def write_daily_summary(
        self,
        trading_date: date,
    ) -> Path:
        """日次サマリーをJSONへ保存する。"""

        summary = self.create_daily_summary(
            trading_date
        )
        path = (
            self.log_directory
            / f"{trading_date.isoformat()}_summary.json"
        )
        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        try:
            path.write_text(
                json.dumps(
                    asdict(summary),
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                    default=self._json_default,
                )
                + "\n",
                encoding="utf-8",
                newline="\n",
            )
        except OSError as error:
            raise LiveOperationLogError(
                "日次サマリーを保存できませんでした。 "
                f"path={path}"
            ) from error

        return path

    def path_for_date(
        self,
        trading_date: date,
    ) -> Path:
        """指定日のJSONLログパスを返す。"""

        return (
            self.log_directory
            / f"{trading_date.isoformat()}.jsonl"
        )

    @staticmethod
    def _count_event(
        entries: tuple[LiveOperationLogEntry, ...],
        event_type: LiveLogEventType,
    ) -> int:
        """イベント種別の件数を返す。"""

        return sum(
            entry.event_type is event_type
            for entry in entries
        )

    @staticmethod
    def _serialize_entry(
        entry: LiveOperationLogEntry,
    ) -> dict[str, Any]:
        """ログをJSON互換形式へ変換する。"""

        return {
            "occurred_at": (
                entry.occurred_at.isoformat()
            ),
            "level": entry.level.value,
            "event_type": entry.event_type.value,
            "message": entry.message,
            "cycle_number": entry.cycle_number,
            "code": entry.code,
            "metadata": entry.metadata,
        }

    @staticmethod
    def _deserialize_entry(
        payload: object,
    ) -> LiveOperationLogEntry:
        """JSON互換形式からログを復元する。"""

        if not isinstance(payload, dict):
            raise TypeError(
                "ログ行は辞書形式である必要があります。"
            )

        metadata = payload.get(
            "metadata",
            {},
        )

        if not isinstance(metadata, dict):
            raise TypeError(
                "メタデータは辞書形式である必要があります。"
            )

        return LiveOperationLogEntry(
            occurred_at=datetime.fromisoformat(
                str(payload["occurred_at"])
            ),
            level=LiveLogLevel(
                str(payload["level"])
            ),
            event_type=LiveLogEventType(
                str(payload["event_type"])
            ),
            message=str(payload["message"]),
            cycle_number=(
                None
                if payload.get("cycle_number") is None
                else int(payload["cycle_number"])
            ),
            code=(
                None
                if payload.get("code") is None
                else str(payload["code"])
            ),
            metadata=dict(metadata),
        )

    @staticmethod
    def _json_default(
        value: object,
    ) -> object:
        """JSON非対応型を変換する。"""

        if isinstance(value, date):
            return value.isoformat()

        raise TypeError(
            f"JSONへ変換できない型です: {type(value)!r}"
        )
