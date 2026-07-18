"""TradingLoopComponentのテスト。"""

from datetime import datetime, timezone

import pytest

from app.application.application_component import (
    ApplicationComponentRegistration,
)
from app.application.application_orchestrator import (
    ApplicationOrchestrator,
)
from app.application.application_runner import (
    ApplicationRunner,
)
from app.application.trading_loop_component import (
    TradingLoopComponent,
)
from app.application.trading_loop_service import (
    TradingLoopService,
)
from app.live.live_orchestrator_models import (
    LiveCycleResult,
    LiveCycleStatus,
)
from app.runtime.session_models import (
    RuntimeSessionStatus,
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
    def run_cycle(
        self,
        *,
        cycle_number,
        codes,
        continue_on_error=True,
    ):
        return LiveCycleResult(
            cycle_number=cycle_number,
            started_at=NOW,
            completed_at=NOW,
            status=LiveCycleStatus.COMPLETED,
            market_result=object(),
            paper_trading_result=None,
            error_message=None,
        )


def create_component():
    session = RuntimeSessionService(
        now_provider=lambda: NOW,
        session_id_provider=lambda: "session-1",
    )
    service = TradingLoopService(
        live_orchestrator=FakeLiveOrchestrator(),
        runtime_session=session,
        now_provider=lambda: NOW,
    )
    component = TradingLoopComponent(
        service=service,
        runtime_session=session,
        codes=("7203", "6758"),
    )
    return component, session


def test_component_starts_runs_cycles_and_stops() -> None:
    component, session = create_component()

    component.start()
    first = component.run_cycle()
    second = component.run_cycle()
    component.stop()

    assert component.component_name == "trading-loop"
    assert first.cycle_number == 1
    assert second.cycle_number == 2
    assert component.is_running is False
    assert component.last_session_report is not None
    assert (
        component.last_session_report
        .snapshot
        .status
        is RuntimeSessionStatus.STOPPED
    )
    assert (
        component.last_session_report
        .total_cycle_count
        == 2
    )


def test_component_rejects_cycle_before_start() -> None:
    component, _session = create_component()

    with pytest.raises(
        RuntimeError,
        match="開始されていません",
    ):
        component.run_cycle()


def test_component_integrates_with_application_orchestrator() -> None:
    component, _session = create_component()
    orchestrator = ApplicationOrchestrator(
        runner=ApplicationRunner(
            now_provider=lambda: NOW,
        ),
        registrations=(
            ApplicationComponentRegistration(
                component=component,
                start_order=10,
            ),
        ),
    )

    started = orchestrator.start()
    cycle = component.run_cycle()
    stopped = orchestrator.shutdown()

    assert started.has_failures is False
    assert cycle.is_successful
    assert (
        stopped.application_report
        .graceful_shutdown
    )
    assert component.last_session_report is not None
