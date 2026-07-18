"""Application Componentの起動・停止・Rollbackを統括する。"""

from __future__ import annotations

from dataclasses import dataclass

from app.application.application_component import (
    ApplicationComponentRegistration,
    ApplicationComponentSnapshot,
    ApplicationComponentState,
)
from app.application.application_models import (
    ApplicationReport,
    ApplicationSnapshot,
    ApplicationStopReason,
)
from app.application.application_runner import (
    ApplicationRunner,
)


@dataclass(frozen=True, slots=True)
class ApplicationOrchestrationResult:
    """Orchestratorの起動または停止結果。"""

    application: ApplicationSnapshot
    components: tuple[ApplicationComponentSnapshot, ...]
    rollback_performed: bool = False

    @property
    def has_failures(self) -> bool:
        """Component失敗があるか返す。"""

        return any(
            item.state is ApplicationComponentState.FAILED
            for item in self.components
        )


@dataclass(frozen=True, slots=True)
class ApplicationShutdownResult:
    """Orchestrator停止結果。"""

    application_report: ApplicationReport
    components: tuple[ApplicationComponentSnapshot, ...]

    @property
    def has_failures(self) -> bool:
        """Component停止失敗があるか返す。"""

        return any(
            item.state is ApplicationComponentState.FAILED
            for item in self.components
        )


class ApplicationOrchestrator:
    """ApplicationRunnerと複数Componentを協調動作させる。"""

    def __init__(
        self,
        *,
        runner: ApplicationRunner,
        registrations: tuple[
            ApplicationComponentRegistration,
            ...
        ] = (),
    ) -> None:
        """Runnerと初期Componentを設定する。"""

        self.runner = runner
        self._registrations: dict[
            str,
            ApplicationComponentRegistration,
        ] = {}
        self._states: dict[
            str,
            ApplicationComponentSnapshot,
        ] = {}

        for registration in registrations:
            self.register(registration)

    def register(
        self,
        registration: ApplicationComponentRegistration,
    ) -> None:
        """Componentを登録する。"""

        name = registration.component_name

        if name in self._registrations:
            raise ValueError(
                "Application Component名が重複しています。 "
                f"component={name}"
            )

        if self.runner.snapshot().state.value != "created":
            raise RuntimeError(
                "Application開始後はComponentを登録できません。"
            )

        self._registrations[name] = registration
        self._states[name] = ApplicationComponentSnapshot(
            component_name=name,
            state=ApplicationComponentState.REGISTERED,
            start_order=registration.start_order,
            stop_order=registration.stop_order,
        )

    def start(
        self,
        *,
        rollback_on_failure: bool = True,
    ) -> ApplicationOrchestrationResult:
        """ApplicationとComponentを順番に開始する。"""

        application = self.runner.start()
        started_names: list[str] = []
        rollback_performed = False

        for registration in self._start_sequence():
            name = registration.component_name
            self._set_state(
                registration,
                ApplicationComponentState.STARTING,
            )

            try:
                registration.component.start()
            except Exception as error:
                self._set_state(
                    registration,
                    ApplicationComponentState.FAILED,
                    error_message=(
                        str(error).strip()
                        or type(error).__name__
                    ),
                )

                if rollback_on_failure:
                    rollback_performed = True
                    self._rollback(started_names)

                application = self.runner.fail(
                    message=(
                        "Application Componentの開始に失敗しました。 "
                        f"component={name}"
                    )
                ).snapshot

                return ApplicationOrchestrationResult(
                    application=application,
                    components=self.component_snapshots(),
                    rollback_performed=rollback_performed,
                )

            self._set_state(
                registration,
                ApplicationComponentState.RUNNING,
            )
            started_names.append(name)

        return ApplicationOrchestrationResult(
            application=application,
            components=self.component_snapshots(),
            rollback_performed=False,
        )

    def shutdown(
        self,
        *,
        reason: ApplicationStopReason = (
            ApplicationStopReason.MANUAL
        ),
        message: str | None = None,
        continue_on_error: bool = True,
    ) -> ApplicationShutdownResult:
        """Componentを逆順で停止してApplicationを終了する。"""

        self.runner.begin_shutdown(
            reason=reason,
            message=message,
        )
        stop_failed = False

        for registration in self._stop_sequence():
            name = registration.component_name
            current = self._states[name]

            if current.state not in {
                ApplicationComponentState.RUNNING,
                ApplicationComponentState.FAILED,
            }:
                continue

            self._set_state(
                registration,
                ApplicationComponentState.STOPPING,
            )

            try:
                registration.component.stop()
            except Exception as error:
                stop_failed = True
                self._set_state(
                    registration,
                    ApplicationComponentState.FAILED,
                    error_message=(
                        str(error).strip()
                        or type(error).__name__
                    ),
                )

                if not continue_on_error:
                    raise
            else:
                self._set_state(
                    registration,
                    ApplicationComponentState.STOPPED,
                )

        report = self.runner.complete_shutdown()

        if stop_failed and report.graceful_shutdown:
            raise RuntimeError(
                "Component停止失敗があるため"
                "Graceful Shutdownとして完了できません。"
            )

        return ApplicationShutdownResult(
            application_report=report,
            components=self.component_snapshots(),
        )

    def component_snapshots(
        self,
    ) -> tuple[ApplicationComponentSnapshot, ...]:
        """Component状態一覧を開始順で返す。"""

        return tuple(
            self._states[
                registration.component_name
            ]
            for registration in self._start_sequence()
        )

    def _rollback(
        self,
        started_names: list[str],
    ) -> None:
        """開始済みComponentを逆順で停止する。"""

        started_set = set(started_names)

        for registration in self._stop_sequence():
            name = registration.component_name

            if name not in started_set:
                continue

            self._set_state(
                registration,
                ApplicationComponentState.STOPPING,
            )

            try:
                registration.component.stop()
            except Exception as error:
                self._set_state(
                    registration,
                    ApplicationComponentState.FAILED,
                    error_message=(
                        str(error).strip()
                        or type(error).__name__
                    ),
                )
            else:
                self._set_state(
                    registration,
                    ApplicationComponentState.STOPPED,
                )

    def _start_sequence(
        self,
    ) -> tuple[ApplicationComponentRegistration, ...]:
        """開始順序を返す。"""

        return tuple(
            sorted(
                self._registrations.values(),
                key=lambda item: (
                    item.start_order,
                    item.component_name,
                ),
            )
        )

    def _stop_sequence(
        self,
    ) -> tuple[ApplicationComponentRegistration, ...]:
        """停止順序を返す。"""

        return tuple(
            sorted(
                self._registrations.values(),
                key=lambda item: (
                    item.stop_order,
                    item.component_name,
                ),
                reverse=True,
            )
        )

    def _set_state(
        self,
        registration: ApplicationComponentRegistration,
        state: ApplicationComponentState,
        *,
        error_message: str | None = None,
    ) -> None:
        """Component状態を更新する。"""

        self._states[
            registration.component_name
        ] = ApplicationComponentSnapshot(
            component_name=registration.component_name,
            state=state,
            start_order=registration.start_order,
            stop_order=registration.stop_order,
            error_message=error_message,
        )
