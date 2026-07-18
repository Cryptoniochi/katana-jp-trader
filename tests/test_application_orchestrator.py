"""ApplicationOrchestratorのテスト。"""

from datetime import datetime, timezone

import pytest

from app.application.application_component import (
    ApplicationComponentRegistration,
    ApplicationComponentState,
)
from app.application.application_models import (
    ApplicationState,
    ApplicationStopReason,
)
from app.application.application_orchestrator import (
    ApplicationOrchestrator,
)
from app.application.application_runner import (
    ApplicationRunner,
)


NOW = datetime(
    2026,
    7,
    18,
    12,
    0,
    tzinfo=timezone.utc,
)


class FakeComponent:
    def __init__(
        self,
        name: str,
        log: list[str],
        *,
        fail_on_start: bool = False,
        fail_on_stop: bool = False,
    ) -> None:
        self._name = name
        self.log = log
        self.fail_on_start = fail_on_start
        self.fail_on_stop = fail_on_stop

    @property
    def component_name(self) -> str:
        return self._name

    def start(self) -> None:
        self.log.append(f"start:{self._name}")

        if self.fail_on_start:
            raise RuntimeError(
                f"start failed: {self._name}"
            )

    def stop(self) -> None:
        self.log.append(f"stop:{self._name}")

        if self.fail_on_stop:
            raise RuntimeError(
                f"stop failed: {self._name}"
            )


def runner() -> ApplicationRunner:
    return ApplicationRunner(
        now_provider=lambda: NOW,
    )


def registration(
    component: FakeComponent,
    order: int,
) -> ApplicationComponentRegistration:
    return ApplicationComponentRegistration(
        component=component,
        start_order=order,
    )


def test_orchestrator_starts_components_in_order() -> None:
    log: list[str] = []
    orchestrator = ApplicationOrchestrator(
        runner=runner(),
        registrations=(
            registration(
                FakeComponent("notification", log),
                30,
            ),
            registration(
                FakeComponent("runtime-session", log),
                10,
            ),
            registration(
                FakeComponent("supervisor", log),
                20,
            ),
        ),
    )

    result = orchestrator.start()

    assert result.application.state is ApplicationState.RUNNING
    assert log == [
        "start:runtime-session",
        "start:supervisor",
        "start:notification",
    ]
    assert all(
        item.state is ApplicationComponentState.RUNNING
        for item in result.components
    )


def test_shutdown_stops_components_in_reverse_order() -> None:
    log: list[str] = []
    orchestrator = ApplicationOrchestrator(
        runner=runner(),
        registrations=(
            registration(
                FakeComponent("first", log),
                1,
            ),
            registration(
                FakeComponent("second", log),
                2,
            ),
            registration(
                FakeComponent("third", log),
                3,
            ),
        ),
    )
    orchestrator.start()
    log.clear()

    result = orchestrator.shutdown(
        reason=ApplicationStopReason.NORMAL
    )

    assert log == [
        "stop:third",
        "stop:second",
        "stop:first",
    ]
    assert result.application_report.graceful_shutdown
    assert all(
        item.state is ApplicationComponentState.STOPPED
        for item in result.components
    )


def test_start_failure_rolls_back_started_components() -> None:
    log: list[str] = []
    orchestrator = ApplicationOrchestrator(
        runner=runner(),
        registrations=(
            registration(
                FakeComponent("first", log),
                1,
            ),
            registration(
                FakeComponent(
                    "second",
                    log,
                    fail_on_start=True,
                ),
                2,
            ),
            registration(
                FakeComponent("third", log),
                3,
            ),
        ),
    )

    result = orchestrator.start()

    assert result.rollback_performed
    assert result.application.state is ApplicationState.FAILED
    assert log == [
        "start:first",
        "start:second",
        "stop:first",
    ]
    states = {
        item.component_name: item.state
        for item in result.components
    }
    assert states["first"] is ApplicationComponentState.STOPPED
    assert states["second"] is ApplicationComponentState.FAILED
    assert states["third"] is ApplicationComponentState.REGISTERED


def test_duplicate_component_name_is_rejected() -> None:
    log: list[str] = []
    first = FakeComponent("same", log)
    second = FakeComponent("same", log)

    with pytest.raises(ValueError, match="重複"):
        ApplicationOrchestrator(
            runner=runner(),
            registrations=(
                registration(first, 1),
                registration(second, 2),
            ),
        )


def test_registration_after_start_is_rejected() -> None:
    log: list[str] = []
    orchestrator = ApplicationOrchestrator(
        runner=runner(),
    )
    orchestrator.start()

    with pytest.raises(RuntimeError, match="開始後"):
        orchestrator.register(
            registration(
                FakeComponent("late", log),
                1,
            )
        )
