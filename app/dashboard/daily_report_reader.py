"""生成済み日次取引レポートをDashboard向けに読み込む。"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


class DailyReportReadError(RuntimeError):
    """日次レポートを読み込めないことを表す。"""


class DailyReportReader:
    """reports/daily配下のJSONレポートを読み込む。"""

    def __init__(
        self,
        report_directory: Path,
    ) -> None:
        self.report_directory = Path(
            report_directory
        )

    def read_latest(self) -> dict[str, Any]:
        """最新日付のレポートを返す。"""

        candidates = self._list_report_files()

        if not candidates:
            return self._unavailable_payload(
                message=(
                    "Daily trading report has not "
                    "been generated yet."
                )
            )

        return self._read_file(
            candidates[-1]
        )

    def read_for_date(
        self,
        report_date: date,
    ) -> dict[str, Any]:
        """指定日のレポートを返す。"""

        path = (
            self.report_directory
            / f"{report_date.isoformat()}.json"
        )

        if not path.exists():
            return self._unavailable_payload(
                message=(
                    "Daily trading report was not found. "
                    f"date={report_date.isoformat()}"
                ),
                report_date=report_date,
            )

        return self._read_file(path)

    def _list_report_files(
        self,
    ) -> list[Path]:
        if not self.report_directory.exists():
            return []

        candidates: list[
            tuple[date, Path]
        ] = []

        for path in self.report_directory.glob(
            "*.json"
        ):
            try:
                report_date = date.fromisoformat(
                    path.stem
                )
            except ValueError:
                continue

            candidates.append(
                (
                    report_date,
                    path,
                )
            )

        candidates.sort(
            key=lambda item: item[0]
        )
        return [
            path
            for _report_date, path in candidates
        ]

    def _read_file(
        self,
        path: Path,
    ) -> dict[str, Any]:
        try:
            payload = json.loads(
                path.read_text(
                    encoding="utf-8"
                )
            )
        except (
            OSError,
            UnicodeError,
            json.JSONDecodeError,
        ) as error:
            raise DailyReportReadError(
                "日次取引レポートを読み込めませんでした。 "
                f"path={path}"
            ) from error

        if not isinstance(payload, dict):
            raise DailyReportReadError(
                "日次取引レポートは辞書形式である必要があります。"
            )

        summary = payload.get(
            "summary",
            {},
        )

        if not isinstance(summary, dict):
            raise DailyReportReadError(
                "summaryは辞書形式である必要があります。"
            )

        return {
            "available": True,
            "source_path": str(path),
            "report_date": payload.get(
                "report_date"
            ),
            "generated_at": payload.get(
                "generated_at"
            ),
            "status": payload.get(
                "status",
                "unknown",
            ),
            "summary": summary,
            "strategy_breakdown": self._normalize_rows(
                payload.get(
                    "strategy_breakdown",
                    [],
                )
            ),
            "symbol_breakdown": self._normalize_rows(
                payload.get(
                    "symbol_breakdown",
                    [],
                )
            ),
            "error_count": int(
                payload.get(
                    "error_count",
                    0,
                )
            ),
            "recovery_count": int(
                payload.get(
                    "recovery_count",
                    0,
                )
            ),
            "notes": [
                str(note)
                for note in payload.get(
                    "notes",
                    [],
                )
            ],
            "message": None,
        }

    @staticmethod
    def _normalize_rows(
        rows: object,
    ) -> list[dict[str, Any]]:
        if not isinstance(rows, list):
            return []

        return [
            dict(row)
            for row in rows
            if isinstance(row, dict)
        ]

    @staticmethod
    def _unavailable_payload(
        *,
        message: str,
        report_date: date | None = None,
    ) -> dict[str, Any]:
        return {
            "available": False,
            "source_path": None,
            "report_date": (
                report_date.isoformat()
                if report_date is not None
                else None
            ),
            "generated_at": datetime.now(
                timezone.utc
            ).isoformat(),
            "status": "not_available",
            "summary": {},
            "strategy_breakdown": [],
            "symbol_breakdown": [],
            "error_count": 0,
            "recovery_count": 0,
            "notes": [],
            "message": message,
        }
