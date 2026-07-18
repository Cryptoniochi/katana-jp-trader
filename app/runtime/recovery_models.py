"""Self-Healing Runtimeの共通モデル。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class RecoveryStatus(StrEnum):
    """復旧処理の状態。"""

    SUCCESS = "success"
    RETRYING = "retrying"
    FAILED = "failed"
    ABORTED = "aborted"


@dataclass(frozen=True, slots=True)
class RecoveryPolicy:
    """復旧処理の再試行Policy。"""

    maximum_attempts: int = 3
    initial_delay_seconds: float = 1.0
    backoff_multiplier: float = 2.0
    maximum_delay_seconds: float = 30.0

    def __post_init__(self) -> None:
        if self.maximum_attempts <= 0:
            raise ValueError(
                "最大試行回数は0より大きい必要があります。"
            )
        if self.initial_delay_seconds < 0:
            raise ValueError(
                "初期待機秒数は0以上である必要があります。"
            )
        if self.backoff_multiplier < 1:
            raise ValueError(
                "Backoff倍率は1以上である必要があります。"
            )
        if self.maximum_delay_seconds < 0:
            raise ValueError(
                "最大待機秒数は0以上である必要があります。"
            )
        if (
            self.maximum_delay_seconds
            < self.initial_delay_seconds
        ):
            raise ValueError(
                "最大待機秒数は初期待機秒数以上である必要があります。"
            )

    def delay_seconds_for_attempt(
        self,
        attempt_number: int,
    ) -> float:
        """指定試行前の待機秒数を返す。"""

        if attempt_number <= 0:
            raise ValueError(
                "試行番号は0より大きい必要があります。"
            )

        return min(
            self.initial_delay_seconds
            * self.backoff_multiplier
            ** (attempt_number - 1),
            self.maximum_delay_seconds,
        )


@dataclass(frozen=True, slots=True)
class RecoveryAttempt:
    """1回分の復旧試行結果。"""

    attempt_number: int
    started_at: datetime
    completed_at: datetime
    successful: bool
    error_message: str | None
    delay_seconds_before_attempt: float

    def __post_init__(self) -> None:
        if self.attempt_number <= 0:
            raise ValueError(
                "試行番号は0より大きい必要があります。"
            )
        if (
            self.started_at.tzinfo is None
            or self.completed_at.tzinfo is None
        ):
            raise ValueError(
                "試行日時にはタイムゾーンが必要です。"
            )
        if self.completed_at < self.started_at:
            raise ValueError(
                "完了日時は開始日時以後である必要があります。"
            )
        if self.delay_seconds_before_attempt < 0:
            raise ValueError(
                "試行前待機秒数は0以上である必要があります。"
            )

        normalized_error = (
            None
            if self.error_message is None
            else self.error_message.strip() or None
        )

        if self.successful and normalized_error is not None:
            raise ValueError(
                "成功した試行にエラーは設定できません。"
            )
        if not self.successful and normalized_error is None:
            raise ValueError(
                "失敗した試行にはエラーが必要です。"
            )

        object.__setattr__(
            self,
            "error_message",
            normalized_error,
        )

    @property
    def duration_seconds(self) -> float:
        return (
            self.completed_at
            - self.started_at
        ).total_seconds()


@dataclass(frozen=True, slots=True)
class RecoveryResult:
    """復旧処理全体の結果。"""

    recovery_name: str
    status: RecoveryStatus
    started_at: datetime
    completed_at: datetime
    attempts: tuple[RecoveryAttempt, ...]
    message: str | None = None

    def __post_init__(self) -> None:
        recovery_name = self.recovery_name.strip()

        if not recovery_name:
            raise ValueError(
                "復旧処理名を指定してください。"
            )
        if (
            self.started_at.tzinfo is None
            or self.completed_at.tzinfo is None
        ):
            raise ValueError(
                "復旧日時にはタイムゾーンが必要です。"
            )
        if self.completed_at < self.started_at:
            raise ValueError(
                "完了日時は開始日時以後である必要があります。"
            )

        normalized_message = (
            None
            if self.message is None
            else self.message.strip() or None
        )

        if (
            self.status is RecoveryStatus.SUCCESS
            and (
                not self.attempts
                or not self.attempts[-1].successful
            )
        ):
            raise ValueError(
                "SUCCESSには成功した最終試行が必要です。"
            )
        if (
            self.status is RecoveryStatus.FAILED
            and (
                not self.attempts
                or self.attempts[-1].successful
            )
        ):
            raise ValueError(
                "FAILEDには失敗した最終試行が必要です。"
            )
        if (
            self.status is RecoveryStatus.ABORTED
            and normalized_message is None
        ):
            raise ValueError(
                "ABORTEDには理由が必要です。"
            )

        object.__setattr__(self, "recovery_name", recovery_name)
        object.__setattr__(self, "message", normalized_message)

    @property
    def attempt_count(self) -> int:
        return len(self.attempts)

    @property
    def succeeded(self) -> bool:
        return self.status is RecoveryStatus.SUCCESS

    @property
    def total_delay_seconds(self) -> float:
        return sum(
            attempt.delay_seconds_before_attempt
            for attempt in self.attempts
        )
