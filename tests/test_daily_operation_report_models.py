"""日次運用レポートモデルのテスト。"""

from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from app.runtime.daily_operation_report_models import (
    DailyOperationReportPaths,
    DailyOperationReportResult,
)


NOW = datetime(
    2026,
    7,
    18,
    0,
    0,
    tzinfo=timezone.utc,
)


def test_paths_require_same_directory() -> None:
    directory = Path("reports/daily/2026-07-18")

    with pytest.raises(ValueError, match="Directory配下"):
        DailyOperationReportPaths(
            trading_date=date(2026, 7, 18),
            directory=directory,
            json_path=Path("other/summary.json"),
            html_path=directory / "summary.html",
        )


def test_result_validates_sizes_and_date() -> None:
    directory = Path("reports/daily/2026-07-18")
    paths = DailyOperationReportPaths(
        trading_date=date(2026, 7, 18),
        directory=directory,
        json_path=directory / "summary.json",
        html_path=directory / "summary.html",
    )
    result = DailyOperationReportResult(
        trading_date=date(2026, 7, 18),
        generated_at=NOW,
        paths=paths,
        json_size_bytes=100,
        html_size_bytes=200,
    )

    assert result.paths.json_path.name == "summary.json"
    assert result.html_size_bytes == 200
