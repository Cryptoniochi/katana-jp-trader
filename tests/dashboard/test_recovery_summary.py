"""RecoverySummaryのユニットテスト。"""

from datetime import datetime, timezone

import pytest

from app.dashboard.recovery_summary import (
    RecoveryStatus,
    RecoverySummary,
)


def test_default_summary_is_healthy() -> None:
    """初期状態は正常かつ成功率100%になる。"""

    summary = RecoverySummary()

    assert summary.broker_attempts == 0
    assert summary.broker_successes == 0
    assert summary.broker_failures == 0

    assert summary.runtime_attempts == 0
    assert summary.runtime_successes == 0
    assert summary.runtime_failures == 0

    assert summary.total_attempts == 0
    assert summary.total_successes == 0
    assert summary.total_failures == 0

    assert summary.success_rate() == 100.0
    assert summary.has_failure() is False
    assert summary.is_healthy() is True

    assert summary.recovery_status is RecoveryStatus.NORMAL
    assert summary.generated_at is not None
    assert summary.generated_at.tzinfo is not None


def test_total_counts_are_aggregated() -> None:
    """BrokerとRuntimeの回数が正しく集計される。"""

    summary = RecoverySummary(
        broker_attempts=3,
        broker_successes=2,
        broker_failures=1,
        runtime_attempts=4,
        runtime_successes=3,
        runtime_failures=1,
        recovery_status=RecoveryStatus.FAILED,
    )

    assert summary.total_attempts == 7
    assert summary.total_successes == 5
    assert summary.total_failures == 2


def test_success_rate_returns_percentage() -> None:
    """成功率がパーセントで返される。"""

    summary = RecoverySummary(
        broker_attempts=3,
        broker_successes=2,
        broker_failures=1,
        runtime_attempts=3,
        runtime_successes=2,
        runtime_failures=1,
        recovery_status=RecoveryStatus.FAILED,
    )

    assert summary.success_rate() == 66.67


def test_has_failure_returns_true_when_failure_exists() -> None:
    """失敗件数がある場合はTrueを返す。"""

    summary = RecoverySummary(
        broker_attempts=1,
        broker_successes=0,
        broker_failures=1,
        recovery_status=RecoveryStatus.FAILED,
    )

    assert summary.has_failure() is True


def test_is_healthy_returns_false_when_status_is_recovering() -> None:
    """回復処理中は失敗がなくても正常とは判定しない。"""

    summary = RecoverySummary(
        recovery_status=RecoveryStatus.RECOVERING,
    )

    assert summary.has_failure() is False
    assert summary.is_healthy() is False


def test_is_healthy_returns_false_when_status_is_failed() -> None:
    """FAILED状態は正常とは判定しない。"""

    summary = RecoverySummary(
        broker_attempts=1,
        broker_successes=0,
        broker_failures=1,
        recovery_status=RecoveryStatus.FAILED,
    )

    assert summary.is_healthy() is False


def test_is_healthy_returns_false_when_failure_remains() -> None:
    """状態がNORMALでも失敗件数が残っていれば正常とは判定しない。"""

    summary = RecoverySummary(
        runtime_attempts=1,
        runtime_successes=0,
        runtime_failures=1,
        recovery_status=RecoveryStatus.NORMAL,
    )

    assert summary.is_healthy() is False


def test_to_dict_returns_json_serializable_structure() -> None:
    """辞書変換結果にDashboard用の情報が含まれる。"""

    broker_recovery = datetime(
        2026,
        7,
        18,
        0,
        10,
        tzinfo=timezone.utc,
    )
    runtime_recovery = datetime(
        2026,
        7,
        18,
        0,
        20,
        tzinfo=timezone.utc,
    )
    generated_at = datetime(
        2026,
        7,
        18,
        0,
        30,
        tzinfo=timezone.utc,
    )

    summary = RecoverySummary(
        broker_attempts=2,
        broker_successes=2,
        broker_failures=0,
        last_broker_recovery=broker_recovery,
        runtime_attempts=1,
        runtime_successes=1,
        runtime_failures=0,
        last_runtime_recovery=runtime_recovery,
        recovery_status=RecoveryStatus.NORMAL,
        generated_at=generated_at,
    )

    result = summary.to_dict()

    assert result == {
        "broker": {
            "attempts": 2,
            "successes": 2,
            "failures": 0,
            "last_recovery": broker_recovery.isoformat(),
        },
        "runtime": {
            "attempts": 1,
            "successes": 1,
            "failures": 0,
            "last_recovery": runtime_recovery.isoformat(),
        },
        "aggregate": {
            "total_attempts": 3,
            "total_successes": 3,
            "total_failures": 0,
            "success_rate": 100.0,
        },
        "recovery_status": "normal",
        "has_failure": False,
        "is_healthy": True,
        "generated_at": generated_at.isoformat(),
    }


@pytest.mark.parametrize(
    "field_name",
    [
        "broker_attempts",
        "broker_successes",
        "broker_failures",
        "runtime_attempts",
        "runtime_successes",
        "runtime_failures",
    ],
)
def test_negative_count_is_rejected(field_name: str) -> None:
    """回数フィールドへ負数を指定できない。"""

    values = {
        "broker_attempts": 0,
        "broker_successes": 0,
        "broker_failures": 0,
        "runtime_attempts": 0,
        "runtime_successes": 0,
        "runtime_failures": 0,
    }
    values[field_name] = -1

    with pytest.raises(
        ValueError,
        match=rf"{field_name} must be greater than or equal to 0",
    ):
        RecoverySummary(**values)


@pytest.mark.parametrize(
    "field_name",
    [
        "broker_attempts",
        "broker_successes",
        "broker_failures",
        "runtime_attempts",
        "runtime_successes",
        "runtime_failures",
    ],
)
def test_non_integer_count_is_rejected(field_name: str) -> None:
    """回数フィールドへ整数以外を指定できない。"""

    values: dict[str, object] = {
        "broker_attempts": 0,
        "broker_successes": 0,
        "broker_failures": 0,
        "runtime_attempts": 0,
        "runtime_successes": 0,
        "runtime_failures": 0,
    }
    values[field_name] = 1.5

    with pytest.raises(
        TypeError,
        match=rf"{field_name} must be an int",
    ):
        RecoverySummary(**values)


def test_boolean_count_is_rejected() -> None:
    """boolはintの派生型だが回数として受け付けない。"""

    with pytest.raises(
        TypeError,
        match="broker_attempts must be an int",
    ):
        RecoverySummary(
            broker_attempts=True,
            broker_successes=1,
        )


def test_broker_attempts_must_match_results() -> None:
    """Broker試行回数と成功・失敗件数の不一致を拒否する。"""

    with pytest.raises(
        ValueError,
        match=(
            "broker_attempts must equal "
            "broker_successes \\+ broker_failures"
        ),
    ):
        RecoverySummary(
            broker_attempts=2,
            broker_successes=1,
            broker_failures=0,
        )


def test_runtime_attempts_must_match_results() -> None:
    """Runtime試行回数と成功・失敗件数の不一致を拒否する。"""

    with pytest.raises(
        ValueError,
        match=(
            "runtime_attempts must equal "
            "runtime_successes \\+ runtime_failures"
        ),
    ):
        RecoverySummary(
            runtime_attempts=3,
            runtime_successes=1,
            runtime_failures=1,
        )


@pytest.mark.parametrize(
    "field_name",
    [
        "last_broker_recovery",
        "last_runtime_recovery",
        "generated_at",
    ],
)
def test_naive_datetime_is_rejected(field_name: str) -> None:
    """タイムゾーン情報を持たない日時を拒否する。"""

    values = {
        field_name: datetime(2026, 7, 18, 9, 0),
    }

    with pytest.raises(
        ValueError,
        match=rf"{field_name} must be timezone-aware",
    ):
        RecoverySummary(**values)


def test_summary_is_immutable() -> None:
    """生成後のRecoverySummaryを変更できない。"""

    summary = RecoverySummary()

    with pytest.raises(AttributeError):
        summary.broker_attempts = 1  # type: ignore[misc]