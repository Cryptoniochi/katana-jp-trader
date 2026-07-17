"""Supervisor異常時にRecoveryと安全停止を制御する。"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Protocol

from app.live.recovery_models import RecoveryResult
from app.supervisor.fault_tolerance_models import (
    FaultToleranceAttempt,
    FaultToleranceDecision,
    FaultTolerancePolicy,
)
from app.supervisor.supervisor_models import (
    SupervisorStatus,
    SupervisorStopReason,
)


class FaultToleranceSupervisor(Protocol):
    """耐障害性フローが利用するSupervisor操作。"""

    def check(self):
        """現在状態を返す。"""

    def restart_decision(self):
        """再起動可否を返す。"""

    def mark_restarted(self):
        """再起動実施を記録する。"""

    def stop(
        self,
        *,
        reason: SupervisorStopReason,
        message: str | None = None,
    ):
        """Workerを停止状態へする。"""


class FaultToleranceRecoveryManager(Protocol):
    """耐障害性フローが利用するRecovery操作。"""

    def recover(
        self,
        *,
        continue_on_error: bool = False,
    ) -> RecoveryResult:
        """復旧処理を実行する。"""


class FaultToleranceService:
    """Supervisor異常を検知して復旧・再起動・安全停止する。"""

    def __init__(
        self,
        *,
        supervisor: FaultToleranceSupervisor,
        recovery_manager: FaultToleranceRecoveryManager,
        policy: FaultTolerancePolicy | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        """依存関係・方針・時計を設定する。"""

        self.supervisor = supervisor
        self.recovery_manager = recovery_manager
        self.policy = policy or FaultTolerancePolicy()
        self.now_provider = (
            now_provider
            if now_provider is not None
            else lambda: datetime.now(timezone.utc)
        )
        self._attempt_number = 0
        self._consecutive_failure_count = 0
        self._history: list[FaultToleranceAttempt] = []

    def run_once(self) -> FaultToleranceAttempt:
        """現在状態を評価し、必要なら復旧を1回実行する。"""

        self._attempt_number += 1
        checked_at = self._current_time()
        supervisor_before = self.supervisor.check()

        if supervisor_before.status not in {
            SupervisorStatus.STALE,
            SupervisorStatus.FAILED,
        }:
            attempt = FaultToleranceAttempt(
                attempt_number=self._attempt_number,
                checked_at=checked_at,
                decision=FaultToleranceDecision.NO_ACTION,
                supervisor_before=supervisor_before,
                supervisor_after=supervisor_before,
                recovery_result=None,
                consecutive_failure_count=(
                    self._consecutive_failure_count
                ),
                next_action_at=None,
                message="Workerは正常で、復旧は不要です。",
            )
            return self._record(attempt)

        restart = self.supervisor.restart_decision()

        if not restart.should_restart:
            supervisor_after = self.supervisor.stop(
                reason=SupervisorStopReason.RESTART_LIMIT,
                message=(
                    restart.message
                    or "再起動できないため安全停止しました。"
                ),
            )
            attempt = FaultToleranceAttempt(
                attempt_number=self._attempt_number,
                checked_at=checked_at,
                decision=FaultToleranceDecision.SAFE_STOP,
                supervisor_before=supervisor_before,
                supervisor_after=supervisor_after,
                recovery_result=None,
                consecutive_failure_count=(
                    self._consecutive_failure_count
                ),
                next_action_at=None,
                message=(
                    restart.message
                    or "再起動上限により安全停止しました。"
                ),
            )
            return self._record(attempt)

        if (
            restart.next_restart_at is not None
            and checked_at < restart.next_restart_at
        ):
            attempt = FaultToleranceAttempt(
                attempt_number=self._attempt_number,
                checked_at=checked_at,
                decision=FaultToleranceDecision.DEFERRED,
                supervisor_before=supervisor_before,
                supervisor_after=supervisor_before,
                recovery_result=None,
                consecutive_failure_count=(
                    self._consecutive_failure_count
                ),
                next_action_at=restart.next_restart_at,
                message="再起動Cooldown中のため復旧を延期しました。",
            )
            return self._record(attempt)

        recovery_result: RecoveryResult | None = None

        try:
            recovery_result = self.recovery_manager.recover(
                continue_on_error=(
                    self.policy.continue_recovery_on_error
                )
            )
        except Exception as error:
            return self._handle_failure(
                checked_at=checked_at,
                supervisor_before=supervisor_before,
                recovery_result=None,
                message=(
                    str(error).strip()
                    or type(error).__name__
                ),
            )

        if not recovery_result.is_successful:
            return self._handle_failure(
                checked_at=checked_at,
                supervisor_before=supervisor_before,
                recovery_result=recovery_result,
                message=(
                    "Recovery処理が正常完了しませんでした。 "
                    f"status={recovery_result.status.value}"
                ),
            )

        supervisor_after = self.supervisor.mark_restarted()
        self._consecutive_failure_count = 0

        attempt = FaultToleranceAttempt(
            attempt_number=self._attempt_number,
            checked_at=checked_at,
            decision=FaultToleranceDecision.RECOVERED,
            supervisor_before=supervisor_before,
            supervisor_after=supervisor_after,
            recovery_result=recovery_result,
            consecutive_failure_count=0,
            next_action_at=None,
            message="Recovery完了後にWorkerを再起動しました。",
        )
        return self._record(attempt)

    def history(self) -> tuple[FaultToleranceAttempt, ...]:
        """耐障害性フローの履歴を返す。"""

        return tuple(self._history)

    def reset_failures(self) -> None:
        """連続復旧失敗回数を0へ戻す。"""

        self._consecutive_failure_count = 0

    def clear_history(self) -> None:
        """履歴を消去する。"""

        self._history.clear()

    def _handle_failure(
        self,
        *,
        checked_at: datetime,
        supervisor_before,
        recovery_result: RecoveryResult | None,
        message: str,
    ) -> FaultToleranceAttempt:
        """復旧失敗を記録し、必要なら安全停止する。"""

        self._consecutive_failure_count += 1

        if (
            self._consecutive_failure_count
            >= self.policy.maximum_consecutive_recovery_failures
        ):
            supervisor_after = self.supervisor.stop(
                reason=SupervisorStopReason.ERROR,
                message=(
                    "連続復旧失敗上限に到達したため"
                    "安全停止しました。"
                ),
            )
            decision = FaultToleranceDecision.SAFE_STOP
            result_message = (
                "連続復旧失敗上限に到達しました。 "
                f"last_error={message}"
            )
        else:
            supervisor_after = self.supervisor.check()
            decision = FaultToleranceDecision.RECOVERY_FAILED
            result_message = (
                "Recoveryに失敗しました。 "
                f"error={message}"
            )

        attempt = FaultToleranceAttempt(
            attempt_number=self._attempt_number,
            checked_at=checked_at,
            decision=decision,
            supervisor_before=supervisor_before,
            supervisor_after=supervisor_after,
            recovery_result=recovery_result,
            consecutive_failure_count=(
                self._consecutive_failure_count
            ),
            next_action_at=None,
            message=result_message,
        )
        return self._record(attempt)

    def _record(
        self,
        attempt: FaultToleranceAttempt,
    ) -> FaultToleranceAttempt:
        """結果を履歴へ追加して返す。"""

        self._history.append(attempt)
        return attempt

    def _current_time(self) -> datetime:
        """UTCへ正規化した現在日時を返す。"""

        current = self.now_provider()

        if current.tzinfo is None:
            raise ValueError(
                "現在日時にはタイムゾーンが必要です。"
            )

        return current.astimezone(timezone.utc)
