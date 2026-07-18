"""Self-Healing Runtimeの再試行処理。"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from time import sleep

from app.runtime.recovery_models import (
    RecoveryAttempt,
    RecoveryPolicy,
    RecoveryResult,
    RecoveryStatus,
)


RecoveryAction = Callable[[], bool | None]
AbortPredicate = Callable[[], bool]
NowProvider = Callable[[], datetime]
Sleeper = Callable[[float], None]


class RecoveryService:
    """Recovery ActionをPolicyに従って再試行する。"""

    def __init__(
        self,
        *,
        policy: RecoveryPolicy | None = None,
        now_provider: NowProvider | None = None,
        sleeper: Sleeper = sleep,
    ) -> None:
        self.policy = (
            policy
            if policy is not None
            else RecoveryPolicy()
        )
        self.now_provider = (
            now_provider
            if now_provider is not None
            else lambda: datetime.now(timezone.utc)
        )
        self.sleeper = sleeper

    def execute(
        self,
        *,
        recovery_name: str,
        action: RecoveryAction,
        should_abort: AbortPredicate | None = None,
    ) -> RecoveryResult:
        """Recovery Actionを成功または上限まで実行する。"""

        name = recovery_name.strip()
        if not name:
            raise ValueError(
                "復旧処理名を指定してください。"
            )

        abort_predicate = (
            should_abort
            if should_abort is not None
            else lambda: False
        )
        started_at = self._current_time()
        attempts: list[RecoveryAttempt] = []

        for attempt_number in range(
            1,
            self.policy.maximum_attempts + 1,
        ):
            if abort_predicate():
                return RecoveryResult(
                    recovery_name=name,
                    status=RecoveryStatus.ABORTED,
                    started_at=started_at,
                    completed_at=self._current_time(),
                    attempts=tuple(attempts),
                    message=(
                        "復旧処理が中止条件により停止されました。"
                    ),
                )

            delay_seconds = (
                0.0
                if attempt_number == 1
                else self.policy.delay_seconds_for_attempt(
                    attempt_number - 1
                )
            )

            if delay_seconds > 0:
                self.sleeper(delay_seconds)

            attempt_started_at = self._current_time()

            try:
                action_result = action()
                successful = (
                    True
                    if action_result is None
                    else bool(action_result)
                )
                if not successful:
                    raise RuntimeError(
                        "Recovery Actionが失敗結果を返しました。"
                    )
            except Exception as error:
                attempts.append(
                    RecoveryAttempt(
                        attempt_number=attempt_number,
                        started_at=attempt_started_at,
                        completed_at=self._current_time(),
                        successful=False,
                        error_message=(
                            str(error).strip()
                            or type(error).__name__
                        ),
                        delay_seconds_before_attempt=(
                            delay_seconds
                        ),
                    )
                )
                continue

            attempts.append(
                RecoveryAttempt(
                    attempt_number=attempt_number,
                    started_at=attempt_started_at,
                    completed_at=self._current_time(),
                    successful=True,
                    error_message=None,
                    delay_seconds_before_attempt=(
                        delay_seconds
                    ),
                )
            )

            return RecoveryResult(
                recovery_name=name,
                status=RecoveryStatus.SUCCESS,
                started_at=started_at,
                completed_at=self._current_time(),
                attempts=tuple(attempts),
            )

        return RecoveryResult(
            recovery_name=name,
            status=RecoveryStatus.FAILED,
            started_at=started_at,
            completed_at=self._current_time(),
            attempts=tuple(attempts),
            message=(
                "最大試行回数までに復旧できませんでした。"
            ),
        )

    def _current_time(self) -> datetime:
        current = self.now_provider()

        if current.tzinfo is None:
            raise ValueError(
                "現在日時にはタイムゾーンが必要です。"
            )

        return current.astimezone(timezone.utc)
