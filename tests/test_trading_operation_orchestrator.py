"""TradingOperationOrchestratorのテスト。"""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.runtime.daily_operation_report_models import (
    DailyOperationReportPaths,
    DailyOperationReportResult,
)
from app.runtime.daily_operation_report_publish_service import (
    DailyOperationReportPublishResult,
)
from app.runtime.paper_trading_daily_repository import (
    PaperTradingDailyRecord,
)
from app.runtime.paper_trading_day_models import (
    PaperTradingDayResult,
    PaperTradingDayStopReason,
)
from app.runtime.paper_trading_runtime_models import (
    PaperTradingDailySummary,
    PaperTradingRuntimeStatus,
)
from app.runtime.trading_operation_orchestrator import (
    TradingOperationOrchestrator,
    TradingOperationOrchestratorSettings,
)


NOW = datetime(
    2026,
    7,
    18,
    0,
    0,
    tzinfo=timezone.utc,
)


def operation_result() -> PaperTradingDayResult:
    """テスト用運用結果を作成する。"""

    summary = PaperTradingDailySummary(
        trading_date=NOW.date(),
        started_at=NOW,
        completed_at=NOW,
        status=PaperTradingRuntimeStatus.COMPLETED,
        records=(),
        initial_equity=1_000_000.0,
        final_equity=1_010_000.0,
    )
    record = PaperTradingDailyRecord(
        trading_date=NOW.date(),
        status=PaperTradingRuntimeStatus.COMPLETED,
        started_at=NOW,
        completed_at=NOW,
        cycle_count=0,
        successful_cycle_count=0,
        failed_cycle_count=0,
        signal_count=0,
        execution_count=0,
        initial_equity=1_000_000.0,
        final_equity=1_010_000.0,
        net_profit_loss=10_000.0,
        return_rate=0.01,
        error_message=None,
        payload={},
        created_at=NOW,
        updated_at=NOW,
    )

    return PaperTradingDayResult(
        trading_date=NOW.date(),
        started_at=NOW,
        completed_at=NOW,
        stop_reason=PaperTradingDayStopReason.MARKET_CLOSED,
        summary=summary,
        record=record,
        dashboard_published=True,
    )


class FakeRunner:
    """テスト用運用Runner。"""

    def __init__(self, log: list[str]) -> None:
        self.log = log

    def run(self) -> PaperTradingDayResult:
        self.log.append("operation")
        return operation_result()


class FakeReportPublisher:
    """テスト用レポートPublisher。"""

    def __init__(
        self,
        log: list[str],
        *,
        raises: bool = False,
    ) -> None:
        self.log = log
        self.raises = raises

    def publish(
        self,
        result: PaperTradingDayResult,
    ) -> DailyOperationReportPublishResult:
        self.log.append("report")

        if self.raises:
            raise RuntimeError("report failed")

        directory = Path(
            "reports/daily/2026-07-18"
        )
        return DailyOperationReportPublishResult(
            report_result=DailyOperationReportResult(
                trading_date=NOW.date(),
                generated_at=NOW,
                paths=DailyOperationReportPaths(
                    trading_date=NOW.date(),
                    directory=directory,
                    json_path=(
                        directory / "summary.json"
                    ),
                    html_path=(
                        directory / "summary.html"
                    ),
                ),
                json_size_bytes=100,
                html_size_bytes=200,
            )
        )


class FakeHook:
    """テスト用後処理Hook。"""

    def __init__(
        self,
        log: list[str],
        name: str,
        *,
        raises: bool = False,
    ) -> None:
        self.log = log
        self.name = name
        self.raises = raises

    def handle(
        self,
        result: PaperTradingDayResult,
    ) -> None:
        self.log.append(self.name)

        if self.raises:
            raise RuntimeError(
                f"{self.name} failed"
            )


def test_orchestrator_runs_in_expected_order() -> None:
    """運用、レポート、Hookの順に実行する。"""

    log: list[str] = []
    orchestrator = TradingOperationOrchestrator(
        operation_runner=FakeRunner(log),
        report_publisher=FakeReportPublisher(log),
        hooks=(
            FakeHook(log, "hook-1"),
            FakeHook(log, "hook-2"),
        ),
    )

    result = orchestrator.run()

    assert log == [
        "operation",
        "report",
        "hook-1",
        "hook-2",
    ]
    assert result.report_published is True
    assert result.completed_hook_count == 2
    assert result.hook_failure_count == 0


def test_report_error_can_be_recorded() -> None:
    """既定ではレポート失敗を結果へ記録して継続する。"""

    log: list[str] = []
    orchestrator = TradingOperationOrchestrator(
        operation_runner=FakeRunner(log),
        report_publisher=FakeReportPublisher(
            log,
            raises=True,
        ),
    )

    result = orchestrator.run()

    assert result.report_published is False
    assert result.report_error_message == (
        "report failed"
    )


def test_hook_error_can_be_recorded() -> None:
    """既定ではHook失敗を記録して後続Hookを続ける。"""

    log: list[str] = []
    orchestrator = TradingOperationOrchestrator(
        operation_runner=FakeRunner(log),
        hooks=(
            FakeHook(
                log,
                "hook-1",
                raises=True,
            ),
            FakeHook(log, "hook-2"),
        ),
    )

    result = orchestrator.run()

    assert log == [
        "operation",
        "hook-1",
        "hook-2",
    ]
    assert result.completed_hook_count == 1
    assert result.hook_error_messages == (
        "hook-1 failed",
    )


def test_strict_report_error_is_raised() -> None:
    """厳格設定ではレポート失敗を送出する。"""

    log: list[str] = []
    orchestrator = TradingOperationOrchestrator(
        operation_runner=FakeRunner(log),
        report_publisher=FakeReportPublisher(
            log,
            raises=True,
        ),
        settings=TradingOperationOrchestratorSettings(
            continue_on_report_error=False
        ),
    )

    with pytest.raises(
        RuntimeError,
        match="report failed",
    ):
        orchestrator.run()
