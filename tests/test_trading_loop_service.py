"""TradingLoopServiceのテスト。"""

from datetime import datetime, timezone

import pytest

from app.application.trading_loop_models import (
    TradingLoopCycleStatus,
)
from app.application.trading_loop_service import (
    TradingLoopService,
)
from app.live.live_orchestrator_models import (
    LiveCycleResult,
    LiveCycleStatus,
)
from app.runtime.resource_integration import (
    RuntimeResourceIntegrationResult,
)
from app.runtime.resource_models import (
    RuntimeResourceSnapshot,
    RuntimeResourceThresholds,
)
from app.runtime.session_service import (
    RuntimeSessionService,
)


NOW = datetime(
    2026,
    7,
    18,
    12,
    0,
    tzinfo=timezone.utc,
)


class FakeLiveOrchestrator:
    def __init__(
        self,
        *,
        failed: bool = False,
        raises: bool = False,
    ) -> None:
        self.failed = failed
        self.raises = raises
        self.calls = []

    def run_cycle(
        self,
        *,
        cycle_number,
        codes,
        continue_on_error=True,
    ):
        self.calls.append(
            (
                cycle_number,
                tuple(codes),
                continue_on_error,
            )
        )

        if self.raises:
            raise RuntimeError("live error")

        status = (
            LiveCycleStatus.FAILED
            if self.failed
            else LiveCycleStatus.COMPLETED
        )

        return LiveCycleResult(
            cycle_number=cycle_number,
            started_at=NOW,
            completed_at=NOW,
            status=status,
            market_result=(
                object()
                if not self.failed
                else None
            ),
            paper_trading_result=None,
            error_message=(
                "live failed"
                if self.failed
                else None
            ),
        )


class FakeResourceIntegration:
    def __init__(
        self,
        *,
        critical: bool = False,
    ) -> None:
        self.critical = critical
        self.calls = []

    def sample_once(
        self,
        *,
        continue_on_notification_error=True,
    ):
        self.calls.append(
            continue_on_notification_error
        )

        thresholds = RuntimeResourceThresholds(
            cpu_warning_percent=50.0,
            cpu_critical_percent=90.0,
            rss_warning_bytes=1000,
            rss_critical_bytes=2000,
            thread_warning_count=10,
            thread_critical_count=20,
        )
        evaluation = RuntimeResourceSnapshot(
            sampled_at=NOW,
            cpu_percent=(
                95.0
                if self.critical
                else 10.0
            ),
            rss_bytes=100,
            vms_bytes=200,
            thread_count=1,
            process_uptime_seconds=3600.0,
        ).evaluate(thresholds)

        return RuntimeResourceIntegrationResult(
            evaluation=evaluation,
            notification_result=None,
            supervisor_snapshot=None,
        )


def runtime_session() -> RuntimeSessionService:
    service = RuntimeSessionService(
        now_provider=lambda: NOW,
        session_id_provider=lambda: "session-1",
    )
    service.start()
    return service


def test_completed_live_cycle_updates_runtime_session() -> None:
    live = FakeLiveOrchestrator()
    resource = FakeResourceIntegration()
    session = runtime_session()
    service = TradingLoopService(
        live_orchestrator=live,
        runtime_session=session,
        resource_integration=resource,
        now_provider=lambda: NOW,
    )

    result = service.run_cycle(
        cycle_number=1,
        codes=("7203", "6758"),
    )

    assert result.status is (
        TradingLoopCycleStatus.COMPLETED
    )
    assert result.runtime_session_snapshot.cycle_count == 1
    assert (
        result.runtime_session_snapshot
        .successful_cycle_count
        == 1
    )
    assert result.runtime_session_snapshot.heartbeat_count == 1
    assert live.calls == [
        (1, ("7203", "6758"), True)
    ]
    assert resource.calls == [True]


def test_failed_live_cycle_is_recorded_as_failure() -> None:
    session = runtime_session()
    service = TradingLoopService(
        live_orchestrator=FakeLiveOrchestrator(
            failed=True
        ),
        runtime_session=session,
        now_provider=lambda: NOW,
    )

    result = service.run_cycle(
        cycle_number=1,
        codes=("7203",),
    )

    assert result.status is (
        TradingLoopCycleStatus.FAILED
    )
    assert result.error_message == "live failed"
    assert (
        result.runtime_session_snapshot
        .failed_cycle_count
        == 1
    )
    assert result.runtime_session_snapshot.error_count == 1


def test_resource_critical_marks_cycle_unsuccessful() -> None:
    session = runtime_session()
    service = TradingLoopService(
        live_orchestrator=FakeLiveOrchestrator(),
        runtime_session=session,
        resource_integration=FakeResourceIntegration(
            critical=True
        ),
        now_provider=lambda: NOW,
    )

    result = service.run_cycle(
        cycle_number=1,
        codes=("7203",),
    )

    assert result.status is (
        TradingLoopCycleStatus.RESOURCE_CRITICAL
    )
    assert (
        result.runtime_session_snapshot
        .failed_cycle_count
        == 1
    )


def test_unexpected_error_can_be_returned_as_failed_cycle() -> None:
    session = runtime_session()
    service = TradingLoopService(
        live_orchestrator=FakeLiveOrchestrator(
            raises=True
        ),
        runtime_session=session,
        now_provider=lambda: NOW,
    )

    result = service.run_cycle(
        cycle_number=1,
        codes=("7203",),
        continue_on_error=True,
    )

    assert result.status is (
        TradingLoopCycleStatus.FAILED
    )
    assert result.error_message == "live error"
    assert (
        result.runtime_session_snapshot
        .failed_cycle_count
        == 1
    )


def test_unexpected_error_can_be_raised() -> None:
    service = TradingLoopService(
        live_orchestrator=FakeLiveOrchestrator(
            raises=True
        ),
        runtime_session=runtime_session(),
        now_provider=lambda: NOW,
    )

    with pytest.raises(
        RuntimeError,
        match="live error",
    ):
        service.run_cycle(
            cycle_number=1,
            codes=("7203",),
            continue_on_error=False,
        )


def test_empty_codes_are_rejected() -> None:
    service = TradingLoopService(
        live_orchestrator=FakeLiveOrchestrator(),
        runtime_session=runtime_session(),
        now_provider=lambda: NOW,
    )

    with pytest.raises(
        ValueError,
        match="監視対象銘柄",
    ):
        service.run_cycle(
            cycle_number=1,
            codes=(),
        )
