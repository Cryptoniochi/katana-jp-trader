"""Project KATANAの子プロセスを一元管理する。"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from collections import deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.runtime.katana_service_models import (
    KatanaServiceStatus,
    ManagedComponentName,
    ManagedComponentState,
    ManagedComponentStatus,
    ServiceEvent,
    ServiceEventType,
)


DEFAULT_STATUS_PATH = Path(
    "reports/service/katana_service_status.json"
)


@dataclass(frozen=True, slots=True)
class ManagedProcessDefinition:
    """管理対象プロセスの起動定義。"""

    name: ManagedComponentName
    command: tuple[str, ...]
    enabled: bool
    restart_on_failure: bool = True
    restart_delay_seconds: float = 10.0
    maximum_restarts: int = 100
    external_health_check: Callable[[], bool] | None = None

    def __post_init__(self) -> None:
        if not self.command:
            raise ValueError(
                "起動コマンドを指定してください。"
            )

        if self.restart_delay_seconds < 0:
            raise ValueError(
                "再起動待機時間は0以上である必要があります。"
            )

        if self.maximum_restarts < 0:
            raise ValueError(
                "最大再起動回数は0以上である必要があります。"
            )


@dataclass(slots=True)
class _ManagedProcess:
    definition: ManagedProcessDefinition
    process: subprocess.Popen | None = None
    restart_count: int = 0
    last_exit_code: int | None = None
    started_at: datetime | None = None
    restart_after_monotonic: float | None = None
    state: ManagedComponentState = (
        ManagedComponentState.STOPPED
    )
    message: str | None = None
    has_started_once: bool = False


class KatanaServiceManager:
    """複数のKATANA子プロセスを監視・再起動する。"""

    def __init__(
        self,
        *,
        definitions: Sequence[
            ManagedProcessDefinition
        ],
        status_path: Path = DEFAULT_STATUS_PATH,
        now_provider: Callable[[], datetime] | None = None,
        monotonic_provider: Callable[[], float] = (
            time.monotonic
        ),
        popen_factory: Callable[..., subprocess.Popen] = (
            subprocess.Popen
        ),
        readiness_probe: Callable[[], object] | None = None,
        readiness_interval_seconds: float = 60.0,
        readiness_change_handler: (
            Callable[[str, str, str | None], None]
            | None
        ) = None,
        event_limit: int = 50,
    ) -> None:
        if readiness_interval_seconds <= 0:
            raise ValueError(
                "Readiness確認間隔は0より大きい必要があります。"
            )

        if event_limit <= 0:
            raise ValueError(
                "イベント保持件数は0より大きい必要があります。"
            )

        self.status_path = Path(status_path)
        self.now_provider = (
            now_provider
            if now_provider is not None
            else lambda: datetime.now(timezone.utc)
        )
        self.monotonic_provider = monotonic_provider
        self.popen_factory = popen_factory
        self.readiness_probe = readiness_probe
        self.readiness_interval_seconds = (
            readiness_interval_seconds
        )
        self.readiness_change_handler = (
            readiness_change_handler
        )
        self._next_readiness_probe_at = 0.0
        self._components = {
            definition.name: _ManagedProcess(
                definition=definition,
                state=(
                    ManagedComponentState.STOPPED
                    if definition.enabled
                    else ManagedComponentState.DISABLED
                ),
            )
            for definition in definitions
        }
        self._stop_requested = False
        self.kabu_station_readiness = "not_checked"
        self.service_started_at = self._current_time()
        self._events: deque[ServiceEvent] = deque(
            maxlen=event_limit
        )
        self._record_event(
            ServiceEventType.SERVICE_STARTED,
            component=None,
            message="KATANA Service Manager started.",
        )

    def set_kabu_station_readiness(
        self,
        value: str,
        *,
        message: str | None = None,
    ) -> None:
        normalized = value.strip()

        if not normalized:
            raise ValueError(
                "kabuステーション状態を指定してください。"
            )

        previous = self.kabu_station_readiness
        changed = normalized != previous
        self.kabu_station_readiness = normalized

        resolved_message = (
            message
            or (
                "kabuステーションReadiness changed "
                f"to {normalized}."
            )
        )

        if changed:
            self._record_event(
                ServiceEventType.READINESS_CHANGED,
                component=None,
                message=resolved_message,
            )
            self._notify_readiness_change(
                previous=previous,
                current=normalized,
                message=resolved_message,
            )

        self.write_status()

    def start_enabled_components(self) -> None:
        for component in self._components.values():
            if component.definition.enabled:
                self._start_component(component)

        self.write_status()

    def request_stop(self) -> None:
        self._stop_requested = True
        self._record_event(
            ServiceEventType.SERVICE_STOPPING,
            component=None,
            message="KATANA Service Manager stopping.",
        )

    def poll_once(self) -> None:
        now_monotonic = self.monotonic_provider()
        self._run_readiness_probe_if_due(
            now_monotonic
        )

        for component in self._components.values():
            if not component.definition.enabled:
                continue

            if component.process is not None:
                exit_code = component.process.poll()

                if exit_code is None:
                    component.state = (
                        ManagedComponentState.RUNNING
                    )
                    continue

                component.last_exit_code = int(
                    exit_code
                )
                component.process = None

                if (
                    exit_code != 0
                    and component.definition.restart_on_failure
                    and component.restart_count
                    < component.definition.maximum_restarts
                    and not self._stop_requested
                ):
                    component.state = (
                        ManagedComponentState.RESTART_WAIT
                    )
                    component.restart_after_monotonic = (
                        now_monotonic
                        + component.definition.restart_delay_seconds
                    )
                    component.message = (
                        "Unexpected exit. "
                        f"exit_code={exit_code}"
                    )
                    self._record_event(
                        ServiceEventType.RESTART_SCHEDULED,
                        component=component.definition.name,
                        message=(
                            f"{component.definition.name.value} "
                            f"exited with code {exit_code}; "
                            "restart scheduled."
                        ),
                    )
                else:
                    component.state = (
                        ManagedComponentState.STOPPED
                        if exit_code == 0
                        else ManagedComponentState.FAILED
                    )
                    component.message = (
                        f"Process exited. exit_code={exit_code}"
                    )
                    self._record_event(
                        (
                            ServiceEventType.COMPONENT_STOPPED
                            if exit_code == 0
                            else ServiceEventType.COMPONENT_FAILED
                        ),
                        component=component.definition.name,
                        message=component.message,
                    )

            elif (
                component.state
                is ManagedComponentState.RUNNING
                and component.process is None
                and component.definition.external_health_check
                is not None
            ):
                try:
                    externally_healthy = bool(
                        component.definition.external_health_check()
                    )
                except Exception:
                    externally_healthy = False

                if externally_healthy:
                    component.message = (
                        "Existing healthy process is being adopted."
                    )
                    continue

                component.state = ManagedComponentState.STARTING
                component.message = (
                    "Adopted process is no longer healthy; "
                    "starting a managed process."
                )
                self._start_component(component)

            elif (
                component.state
                is ManagedComponentState.RESTART_WAIT
                and component.restart_after_monotonic
                is not None
                and now_monotonic
                >= component.restart_after_monotonic
                and not self._stop_requested
            ):
                component.restart_count += 1
                self._start_component(component)

        self.write_status()

    def stop_all(
        self,
        *,
        timeout_seconds: float = 15.0,
    ) -> None:
        self._stop_requested = True

        for component in self._components.values():
            process = component.process

            if process is None:
                continue

            if process.poll() is None:
                process.terminate()

        deadline = (
            self.monotonic_provider()
            + timeout_seconds
        )

        for component in self._components.values():
            process = component.process

            if process is None:
                continue

            remaining = max(
                0.0,
                deadline - self.monotonic_provider(),
            )

            try:
                process.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()

            component.last_exit_code = process.returncode
            component.process = None
            component.state = (
                ManagedComponentState.STOPPED
            )
            component.message = (
                "Stopped by Service Manager."
            )
            self._record_event(
                ServiceEventType.COMPONENT_STOPPED,
                component=component.definition.name,
                message=component.message,
            )

        self.write_status()

    def run_forever(
        self,
        *,
        poll_interval_seconds: float = 5.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if poll_interval_seconds <= 0:
            raise ValueError(
                "監視間隔は0より大きい必要があります。"
            )

        self.start_enabled_components()

        try:
            while not self._stop_requested:
                self.poll_once()
                sleep(poll_interval_seconds)
        finally:
            self.stop_all()

    def create_status(self) -> KatanaServiceStatus:
        current_time = self._current_time()
        statuses = tuple(
            ManagedComponentStatus(
                name=component.definition.name,
                state=component.state,
                enabled=component.definition.enabled,
                process_id=(
                    component.process.pid
                    if component.process is not None
                    and component.process.poll() is None
                    else None
                ),
                restart_count=component.restart_count,
                last_exit_code=component.last_exit_code,
                started_at=component.started_at,
                updated_at=current_time,
                message=component.message,
            )
            for component in self._components.values()
        )
        enabled = [
            item
            for item in statuses
            if item.enabled
        ]
        service_state = (
            "healthy"
            if enabled
            and all(
                item.state
                is ManagedComponentState.RUNNING
                for item in enabled
            )
            else (
                "degraded"
                if enabled
                else "idle"
            )
        )
        uptime_seconds = max(
            0.0,
            (
                current_time
                - self.service_started_at
            ).total_seconds(),
        )

        return KatanaServiceStatus(
            generated_at=current_time,
            service_state=service_state,
            kabu_station_readiness=(
                self.kabu_station_readiness
            ),
            components=statuses,
            service_started_at=(
                self.service_started_at
            ),
            uptime_seconds=uptime_seconds,
            recent_events=tuple(self._events),
        )

    def write_status(self) -> None:
        self.status_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        temporary_path = self.status_path.with_suffix(
            self.status_path.suffix + ".tmp"
        )
        temporary_path.write_text(
            json.dumps(
                self.create_status().to_dict(),
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        temporary_path.replace(self.status_path)

    def _start_component(
        self,
        component: _ManagedProcess,
    ) -> None:
        health_check = (
            component.definition.external_health_check
        )

        if health_check is not None:
            try:
                externally_healthy = bool(health_check())
            except Exception:
                externally_healthy = False

            if externally_healthy:
                component.process = None
                component.started_at = self._current_time()
                component.restart_after_monotonic = None
                component.state = ManagedComponentState.RUNNING
                component.message = (
                    "Existing healthy process is being adopted."
                )
                component.has_started_once = True
                self._record_event(
                    ServiceEventType.COMPONENT_STARTED,
                    component=component.definition.name,
                    message=(
                        f"{component.definition.name.value} "
                        "adopted an existing healthy process."
                    ),
                )
                return

        was_restart = component.has_started_once
        component.state = (
            ManagedComponentState.STARTING
        )
        component.message = None
        self.write_status()

        try:
            process = self.popen_factory(
                list(component.definition.command),
                cwd=Path.cwd(),
            )
        except OSError as error:
            component.process = None
            component.state = (
                ManagedComponentState.FAILED
            )
            component.message = str(error)
            self._record_event(
                ServiceEventType.COMPONENT_FAILED,
                component=component.definition.name,
                message=str(error),
            )
            self.write_status()
            return

        component.process = process
        component.started_at = self._current_time()
        component.restart_after_monotonic = None
        component.state = (
            ManagedComponentState.RUNNING
        )
        component.message = None
        component.has_started_once = True
        self._record_event(
            (
                ServiceEventType.RESTART_COMPLETED
                if was_restart
                else ServiceEventType.COMPONENT_STARTED
            ),
            component=component.definition.name,
            message=(
                f"{component.definition.name.value} "
                f"started. pid={process.pid}"
            ),
        )

    def _run_readiness_probe_if_due(
        self,
        now_monotonic: float,
    ) -> None:
        if self.readiness_probe is None:
            return

        if (
            now_monotonic
            < self._next_readiness_probe_at
        ):
            return

        self._next_readiness_probe_at = (
            now_monotonic
            + self.readiness_interval_seconds
        )

        try:
            result = self.readiness_probe()
            state = str(
                getattr(
                    result,
                    "state",
                    "error",
                )
            )
            message = str(
                getattr(
                    result,
                    "message",
                    state,
                )
            )
        except Exception as error:
            state = "error"
            message = str(error)

        self.set_kabu_station_readiness(
            state,
            message=message,
        )

    def _notify_readiness_change(
        self,
        *,
        previous: str,
        current: str,
        message: str | None,
    ) -> None:
        """Readiness状態変化を外部ハンドラーへ通知する。"""

        if self.readiness_change_handler is None:
            return

        try:
            self.readiness_change_handler(
                previous,
                current,
                message,
            )
        except Exception as error:
            self._record_event(
                ServiceEventType.READINESS_CHANGED,
                component=None,
                message=(
                    "Readiness change notification failed. "
                    f"error={type(error).__name__}: {error}"
                ),
            )

    def _record_event(
        self,
        event_type: ServiceEventType,
        *,
        component: ManagedComponentName | None,
        message: str,
    ) -> None:
        self._events.appendleft(
            ServiceEvent(
                occurred_at=self._current_time(),
                event_type=event_type,
                component=component,
                message=message,
            )
        )

    def _current_time(self) -> datetime:
        value = self.now_provider()

        if value.tzinfo is None:
            raise ValueError(
                "現在日時にはタイムゾーンが必要です。"
            )

        return value.astimezone(timezone.utc)


def build_dashboard_command(
    *,
    database_path: Path,
    host: str,
    port: int,
    service_status_path: Path,
) -> tuple[str, ...]:
    """Service Manager配下でDashboard本体を直接起動する。"""

    return (
        sys.executable,
        "-m",
        "app.dashboard",
        "--host",
        host,
        "--port",
        str(port),
        "--database",
        str(database_path),
        "--service-status",
        str(service_status_path),
        "--no-browser",
    )


def build_paper_trading_command(
    *,
    database_path: Path,
    watchlist_path: Path,
    strategies: Sequence[str],
) -> tuple[str, ...]:
    """kabuステーション利用のPaper Trading起動コマンドを作る。"""

    command = [
        sys.executable,
        "-m",
        "app.run_paper_trading",
        "--database-path",
        str(database_path),
        "--watchlist",
        str(watchlist_path),
        "--market-data-mode",
        "kabu-station-realtime",
    ]

    for strategy in strategies:
        command.extend(
            [
                "--strategy",
                strategy,
            ]
        )

    return tuple(command)



def build_scheduled_paper_trading_command(
    *,
    database_path: Path,
    watchlist_path: Path,
    strategies: Sequence[str],
    enabled: bool,
) -> tuple[str, ...]:
    """営業日Paper Tradingスケジューラの起動コマンドを作る。"""

    command = [
        sys.executable,
        "-m",
        "app.run_scheduled_paper_trading",
    ]

    if enabled:
        command.append("--enable")

    command.extend(
        [
            "--database-path",
            str(database_path),
            "--watchlist",
            str(watchlist_path),
            "--market-data-mode",
            "kabu-station-realtime",
        ]
    )

    for strategy in strategies:
        command.extend(
            [
                "--strategy",
                strategy,
            ]
        )

    return tuple(command)



def build_daily_report_scheduler_command(
    *,
    database_path: Path,
    enabled: bool,
) -> tuple[str, ...]:
    """Daily Report自動生成・通知スケジューラの起動コマンド。"""

    command = [
        sys.executable,
        "-m",
        "app.run_daily_report_scheduler",
        "--database-path",
        str(database_path),
    ]

    if enabled:
        command.append("--enable")

    return tuple(command)



def build_morning_preflight_scheduler_command(
    *,
    enabled: bool,
) -> tuple[str, ...]:
    """Morning Pre-Flightスケジューラ起動コマンド。"""

    command = [
        sys.executable,
        "-m",
        "app.run_morning_preflight_scheduler",
    ]

    if enabled:
        command.append("--enable")

    return tuple(command)



def build_dynamic_watchlist_scheduler_command(
    *,
    database_path: Path,
    watchlist_path: Path,
    enabled: bool,
) -> tuple[str, ...]:
    """Dynamic Watchlistスケジューラ起動コマンド。"""

    command = [
        sys.executable,
        "-m",
        "app.run_dynamic_watchlist_scheduler",
        "--database-path",
        str(database_path),
        "--watchlist-path",
        str(watchlist_path),
        "--minimum-symbols",
        "5",
        "--maximum-symbols",
        "50",
        "--capital-limit",
        "1000000",
        "--purchase-budget",
        "950000",
    ]

    if enabled:
        command.append("--enable")

    return tuple(command)

def build_universe_daily_scheduler_command(
    *,
    database_path: Path,
    enabled: bool,
) -> tuple[str, ...]:
    """Universe Daily Scheduler起動コマンド。"""

    command = [
        sys.executable,
        "-m",
        "app.run_universe_daily_scheduler",
        "--database-path",
        str(database_path),
    ]

    if enabled:
        command.append("--enable")

    return tuple(command)

