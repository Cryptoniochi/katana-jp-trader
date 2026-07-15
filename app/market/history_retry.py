"""履歴データ取込で使用する再試行処理。"""

from collections.abc import Callable
from dataclasses import dataclass
from time import sleep


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """再試行回数と待機時間を保持する。"""

    max_attempts: int = 3
    initial_delay_seconds: float = 2.0
    backoff_multiplier: float = 2.0
    maximum_delay_seconds: float = 30.0

    def __post_init__(self) -> None:
        """不正な再試行条件を拒否する。"""

        if self.max_attempts <= 0:
            raise ValueError("最大試行回数は0より大きい必要があります。")

        if self.initial_delay_seconds < 0:
            raise ValueError("初期待機秒数は0以上である必要があります。")

        if self.backoff_multiplier < 1:
            raise ValueError("待機時間倍率は1以上である必要があります。")

        if self.maximum_delay_seconds < 0:
            raise ValueError("最大待機秒数は0以上である必要があります。")


@dataclass(frozen=True, slots=True)
class RetryAttempt:
    """失敗した1回の試行を表す。"""

    attempt_number: int
    delay_seconds: float
    error: Exception


class RetryExhaustedError(RuntimeError):
    """すべての再試行に失敗したことを表す。"""

    def __init__(
        self,
        attempts: list[RetryAttempt],
    ) -> None:
        """失敗した試行一覧を保持する。"""

        self.attempts = attempts

        if attempts:
            last_error = attempts[-1].error
            message = (
                "最大試行回数に達しました。"
                f" attempts={len(attempts)} "
                f"last_error={last_error}"
            )
        else:
            message = "再試行結果を取得できませんでした。"

        super().__init__(message)

    @property
    def last_error(self) -> Exception | None:
        """最後に発生した例外を返す。"""

        if not self.attempts:
            return None

        return self.attempts[-1].error


RetryCallback = Callable[[RetryAttempt], None]


def run_with_retry[ResultType](
    operation: Callable[[], ResultType],
    *,
    policy: RetryPolicy,
    retry_exceptions: tuple[type[Exception], ...],
    sleeper: Callable[[float], None] = sleep,
    retry_callback: RetryCallback | None = None,
) -> ResultType:
    """一時的な例外に対して処理を再試行する。"""

    if not retry_exceptions:
        raise ValueError("再試行対象の例外を1件以上指定してください。")

    attempts: list[RetryAttempt] = []
    delay_seconds = policy.initial_delay_seconds

    for attempt_number in range(
        1,
        policy.max_attempts + 1,
    ):
        try:
            return operation()

        except retry_exceptions as error:
            is_last_attempt = attempt_number >= policy.max_attempts

            attempt = RetryAttempt(
                attempt_number=attempt_number,
                delay_seconds=(0.0 if is_last_attempt else delay_seconds),
                error=error,
            )

            attempts.append(attempt)

            if retry_callback is not None:
                retry_callback(attempt)

            if is_last_attempt:
                raise RetryExhaustedError(attempts) from error

            sleeper(delay_seconds)

            delay_seconds = min(
                delay_seconds * policy.backoff_multiplier,
                policy.maximum_delay_seconds,
            )

    raise RetryExhaustedError(attempts)
