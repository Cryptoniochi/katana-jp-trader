"""ApplicationRunnerのテスト。"""

from datetime import datetime, timedelta, timezone

import pytest

from app.application.application_models import (
    ApplicationState,
    ApplicationStopReason,
)
from app.application.application_runner import (
    ApplicationRunner,
)


BASE = datetime(
    2026,
    7,
    18,
    12,
    0,
    tzinfo=timezone.utc,
)


class Clock:
    def __init__(self) -> None:
        self.current = BASE

    def __call__(self) -> datetime:
        return self.current


def create_runner(clock: Clock) -> ApplicationRunner:
    return ApplicationRunner(
        application_name="Project KATANA",
        now_provider=clock,
    )


def test_runner_starts_from_created_state() -> None:
    clock = Clock()
    runner = create_runner(clock)

    assert runner.snapshot().state is ApplicationState.CREATED

    snapshot = runner.start()

    assert snapshot.state is ApplicationState.RUNNING
    assert snapshot.started_at == BASE
    assert snapshot.is_running


def test_runner_performs_graceful_shutdown() -> None:
    clock = Clock()
    runner = create_runner(clock)
    runner.start()

    clock.current += timedelta(seconds=10)
    stopping = runner.begin_shutdown(
        reason=ApplicationStopReason.SIGNAL,
        message="SIGTERM",
    )

    assert stopping.state is ApplicationState.STOPPING
    assert stopping.stopping_at == clock.current
    assert stopping.message == "SIGTERM"

    clock.current += timedelta(seconds=5)
    report = runner.complete_shutdown()

    assert report.graceful_shutdown
    assert report.snapshot.state is ApplicationState.STOPPED
    assert report.snapshot.stopped_at == clock.current
    assert report.snapshot.stop_reason is (
        ApplicationStopReason.SIGNAL
    )
    assert report.snapshot.uptime_seconds == 15.0


def test_stop_is_convenience_graceful_shutdown() -> None:
    clock = Clock()
    runner = create_runner(clock)
    runner.start()
    clock.current += timedelta(seconds=20)

    report = runner.stop(
        reason=ApplicationStopReason.NORMAL
    )

    assert report.graceful_shutdown
    assert report.snapshot.state is ApplicationState.STOPPED
    assert report.snapshot.uptime_seconds == 20.0


def test_fail_creates_failed_report() -> None:
    clock = Clock()
    runner = create_runner(clock)
    runner.start()
    clock.current += timedelta(seconds=3)

    report = runner.fail(
        message="startup dependency failed"
    )

    assert report.graceful_shutdown is False
    assert report.snapshot.state is ApplicationState.FAILED
    assert report.snapshot.stop_reason is (
        ApplicationStopReason.ERROR
    )
    assert report.snapshot.message == (
        "startup dependency failed"
    )


def test_invalid_transitions_are_rejected() -> None:
    clock = Clock()
    runner = create_runner(clock)

    with pytest.raises(RuntimeError):
        runner.stop()

    runner.start()

    with pytest.raises(RuntimeError):
        runner.start()

    runner.stop()

    with pytest.raises(RuntimeError):
        runner.begin_shutdown()


def test_naive_clock_is_rejected() -> None:
    with pytest.raises(
        ValueError,
        match="タイムゾーン",
    ):
        ApplicationRunner(
            now_provider=lambda: datetime(2026, 7, 18)
        )
