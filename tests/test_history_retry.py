"""履歴取込の再試行処理をテストする。"""

import pytest

from app.market.history_retry import (
    RetryExhaustedError,
    RetryPolicy,
    run_with_retry,
)


class TemporaryError(RuntimeError):
    """テスト用の一時エラー。"""


def test_retry_returns_first_success() -> None:
    """最初に成功した場合は再試行しない。"""

    call_count = 0
    delays: list[float] = []

    def operation() -> str:
        nonlocal call_count
        call_count += 1
        return "success"

    result = run_with_retry(
        operation,
        policy=RetryPolicy(
            max_attempts=3,
        ),
        retry_exceptions=(TemporaryError,),
        sleeper=delays.append,
    )

    assert result == "success"
    assert call_count == 1
    assert delays == []


def test_retry_succeeds_after_temporary_errors() -> None:
    """一時エラー後に成功できる。"""

    call_count = 0
    delays: list[float] = []

    def operation() -> str:
        nonlocal call_count
        call_count += 1

        if call_count < 3:
            raise TemporaryError(f"temporary {call_count}")

        return "success"

    result = run_with_retry(
        operation,
        policy=RetryPolicy(
            max_attempts=3,
            initial_delay_seconds=1.0,
            backoff_multiplier=2.0,
            maximum_delay_seconds=10.0,
        ),
        retry_exceptions=(TemporaryError,),
        sleeper=delays.append,
    )

    assert result == "success"
    assert call_count == 3
    assert delays == [
        1.0,
        2.0,
    ]


def test_retry_raises_after_max_attempts() -> None:
    """最大回数まで失敗したら専用例外を返す。"""

    call_count = 0
    delays: list[float] = []

    def operation() -> None:
        nonlocal call_count
        call_count += 1
        raise TemporaryError("failed")

    with pytest.raises(
        RetryExhaustedError,
    ) as error_info:
        run_with_retry(
            operation,
            policy=RetryPolicy(
                max_attempts=3,
                initial_delay_seconds=1.0,
                backoff_multiplier=2.0,
            ),
            retry_exceptions=(TemporaryError,),
            sleeper=delays.append,
        )

    assert call_count == 3
    assert delays == [
        1.0,
        2.0,
    ]

    error = error_info.value

    assert len(error.attempts) == 3
    assert isinstance(
        error.last_error,
        TemporaryError,
    )


def test_retry_does_not_catch_unlisted_error() -> None:
    """対象外の例外はそのまま送出する。"""

    def operation() -> None:
        raise ValueError("invalid")

    with pytest.raises(
        ValueError,
        match="invalid",
    ):
        run_with_retry(
            operation,
            policy=RetryPolicy(),
            retry_exceptions=(TemporaryError,),
            sleeper=lambda _seconds: None,
        )


def test_retry_caps_delay() -> None:
    """待機時間を最大値以下に抑える。"""

    delays: list[float] = []

    def operation() -> None:
        raise TemporaryError("failed")

    with pytest.raises(
        RetryExhaustedError,
    ):
        run_with_retry(
            operation,
            policy=RetryPolicy(
                max_attempts=5,
                initial_delay_seconds=4.0,
                backoff_multiplier=3.0,
                maximum_delay_seconds=10.0,
            ),
            retry_exceptions=(TemporaryError,),
            sleeper=delays.append,
        )

    assert delays == [
        4.0,
        10.0,
        10.0,
        10.0,
    ]


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        (
            {
                "max_attempts": 0,
            },
            "最大試行回数",
        ),
        (
            {
                "initial_delay_seconds": -1,
            },
            "初期待機秒数",
        ),
        (
            {
                "backoff_multiplier": 0.5,
            },
            "待機時間倍率",
        ),
        (
            {
                "maximum_delay_seconds": -1,
            },
            "最大待機秒数",
        ),
    ],
)
def test_retry_policy_rejects_invalid_values(
    arguments: dict[str, float | int],
    message: str,
) -> None:
    """不正な再試行条件を拒否する。"""

    with pytest.raises(
        ValueError,
        match=message,
    ):
        RetryPolicy(**arguments)
