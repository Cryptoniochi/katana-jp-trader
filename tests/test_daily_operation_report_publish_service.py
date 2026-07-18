"""DailyOperationReportPublishServiceのテスト。"""

from datetime import datetime, timezone
from pathlib import Path

from app.runtime.daily_operation_report_models import (
    DailyOperationReportPaths,
    DailyOperationReportResult,
)
from app.runtime.daily_operation_report_publish_service import (
    DailyOperationReportPublishService,
)


NOW = datetime(
    2026,
    7,
    18,
    0,
    0,
    tzinfo=timezone.utc,
)


class FakeGenerator:
    def __init__(self) -> None:
        self.results = []

    def generate(self, result):
        self.results.append(result)
        directory = Path("reports/daily/2026-07-18")
        return DailyOperationReportResult(
            trading_date=NOW.date(),
            generated_at=NOW,
            paths=DailyOperationReportPaths(
                trading_date=NOW.date(),
                directory=directory,
                json_path=directory / "summary.json",
                html_path=directory / "summary.html",
            ),
            json_size_bytes=100,
            html_size_bytes=200,
        )


def test_publish_service_delegates_to_generator() -> None:
    generator = FakeGenerator()
    service = DailyOperationReportPublishService(
        report_generator=generator
    )
    operation_result = object()

    result = service.publish(operation_result)

    assert generator.results == [operation_result]
    assert result.report_result.json_size_bytes == 100
    assert result.report_result.html_size_bytes == 200
