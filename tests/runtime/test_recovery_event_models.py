"""RecoveryEvent共通モデルのテスト。"""

from datetime import datetime, timedelta, timezone

import pytest

from app.runtime.recovery_event_models import (
    RecoveryEvent,
    RecoveryEventCategory,
    RecoveryEventStatus,
    RecoverySource,
)


NOW = datetime(
    2026,
    7,
    18,
    12,
    0,
    tzinfo=timezone.utc,
)


def make_event(
    *,
    source: RecoverySource = RecoverySource.RUNTIME,
    category: RecoveryEventCategory = (
        RecoveryEventCategory.RESTART
    ),
    status: RecoveryEventStatus = (
        RecoveryEventStatus.SUCCEEDED
    ),
    name: str = "runtime restart",
    started_at: datetime = NOW,
    completed_at: datetime | None = (
        NOW + timedelta(seconds=3)
    ),
    message: str | None = None,
    metadata: dict[str, object] | None = None,
) -> RecoveryEvent:
    """テスト用RecoveryEventを生成する。"""

    return RecoveryEvent(
        source=source,
        category=category,
        status=status,
        name=name,
        started_at=started_at,
        completed_at=completed_at,
        message=message,
        metadata=(
            {}
            if metadata is None
            else metadata
        ),
    )


def test_event_keeps_common_recovery_information() -> None:
    """共通Recovery情報を保持できる。"""

    event = make_event(
        metadata={
            "runtime_name": "paper-runtime",
            "attempt_count": 2,
        }
    )

    assert event.source is RecoverySource.RUNTIME
    assert (
        event.category
        is RecoveryEventCategory.RESTART
    )
    assert (
        event.status
        is RecoveryEventStatus.SUCCEEDED
    )
    assert event.name == "runtime restart"
    assert event.started_at == NOW
    assert event.completed_at == (
        NOW + timedelta(seconds=3)
    )
    assert event.message is None
    assert event.event_id
    assert event.metadata == {
        "runtime_name": "paper-runtime",
        "attempt_count": 2,
    }


def test_event_normalizes_text_values() -> None:
    """文字列の前後空白を除去する。"""

    event = make_event(
        name="  broker reconnect  ",
        message="  reconnect completed  ",
    )

    assert event.name == "broker reconnect"
    assert event.message == "reconnect completed"


def test_started_event_is_not_terminal() -> None:
    """開始イベントは未完了として扱う。"""

    event = make_event(
        status=RecoveryEventStatus.STARTED,
        completed_at=None,
    )

    assert event.is_terminal is False
    assert event.succeeded is False
    assert event.failed is False
    assert event.duration_seconds is None


def test_retrying_event_is_not_terminal() -> None:
    """再試行中イベントは未完了として扱う。"""

    event = make_event(
        status=RecoveryEventStatus.RETRYING,
        completed_at=None,
        message="retrying after broker error",
    )

    assert event.is_terminal is False
    assert event.succeeded is False
    assert event.failed is False


@pytest.mark.parametrize(
    "status",
    [
        RecoveryEventStatus.SUCCEEDED,
        RecoveryEventStatus.FAILED,
        RecoveryEventStatus.ABORTED,
        RecoveryEventStatus.SKIPPED,
    ],
)
def test_terminal_statuses_are_terminal(
    status: RecoveryEventStatus,
) -> None:
    """終了状態を正しく判定する。"""

    message = (
        "recovery did not complete"
        if status
        in {
            RecoveryEventStatus.FAILED,
            RecoveryEventStatus.ABORTED,
        }
        else None
    )

    event = make_event(
        status=status,
        message=message,
    )

    assert event.is_terminal is True


def test_success_event_reports_success() -> None:
    """成功イベントを判定できる。"""

    event = make_event()

    assert event.succeeded is True
    assert event.failed is False


@pytest.mark.parametrize(
    "status",
    [
        RecoveryEventStatus.FAILED,
        RecoveryEventStatus.ABORTED,
    ],
)
def test_failed_event_reports_failure(
    status: RecoveryEventStatus,
) -> None:
    """失敗・中断イベントを異常として判定する。"""

    event = make_event(
        status=status,
        message="recovery failed",
    )

    assert event.succeeded is False
    assert event.failed is True


def test_event_calculates_duration() -> None:
    """開始から完了までの秒数を返す。"""

    event = make_event(
        completed_at=NOW + timedelta(seconds=4.5)
    )

    assert event.duration_seconds == pytest.approx(
        4.5
    )


def test_metadata_is_copied_and_read_only() -> None:
    """Metadataは外部変更の影響を受けず変更不可となる。"""

    metadata = {
        "attempt_count": 1,
    }

    event = make_event(
        metadata=metadata
    )
    metadata["attempt_count"] = 99

    assert event.metadata["attempt_count"] == 1

    with pytest.raises(TypeError):
        event.metadata["attempt_count"] = 2


def test_metadata_value_returns_value_or_default() -> None:
    """Metadata値とデフォルト値を取得できる。"""

    event = make_event(
        metadata={
            "broker_name": "paper",
        }
    )

    assert (
        event.metadata_value("broker_name")
        == "paper"
    )
    assert (
        event.metadata_value(
            "missing",
            "default",
        )
        == "default"
    )


def test_event_rejects_empty_name() -> None:
    """空のイベント名を拒否する。"""

    with pytest.raises(
        ValueError,
        match="name must not be empty",
    ):
        make_event(name="   ")


def test_event_rejects_naive_started_at() -> None:
    """Timezoneなしの開始日時を拒否する。"""

    with pytest.raises(
        ValueError,
        match="started_at must be timezone-aware",
    ):
        make_event(
            started_at=datetime(
                2026,
                7,
                18,
                12,
                0,
            )
        )


def test_event_rejects_naive_completed_at() -> None:
    """Timezoneなしの完了日時を拒否する。"""

    with pytest.raises(
        ValueError,
        match="completed_at must be timezone-aware",
    ):
        make_event(
            completed_at=datetime(
                2026,
                7,
                18,
                12,
                1,
            )
        )


def test_event_rejects_completion_before_start() -> None:
    """開始日時より前の完了日時を拒否する。"""

    with pytest.raises(
        ValueError,
        match=(
            "completed_at must be greater than or "
            "equal to started_at"
        ),
    ):
        make_event(
            completed_at=NOW - timedelta(seconds=1)
        )


@pytest.mark.parametrize(
    "status",
    [
        RecoveryEventStatus.STARTED,
        RecoveryEventStatus.RETRYING,
    ],
)
def test_active_event_rejects_completed_at(
    status: RecoveryEventStatus,
) -> None:
    """進行中状態に完了日時を設定できない。"""

    with pytest.raises(
        ValueError,
        match=(
            "active RecoveryEvent must not have "
            "completed_at"
        ),
    ):
        make_event(
            status=status,
            completed_at=NOW,
        )


@pytest.mark.parametrize(
    "status",
    [
        RecoveryEventStatus.SUCCEEDED,
        RecoveryEventStatus.FAILED,
        RecoveryEventStatus.ABORTED,
        RecoveryEventStatus.SKIPPED,
    ],
)
def test_terminal_event_requires_completed_at(
    status: RecoveryEventStatus,
) -> None:
    """終了状態には完了日時が必要となる。"""

    message = (
        "recovery failed"
        if status
        in {
            RecoveryEventStatus.FAILED,
            RecoveryEventStatus.ABORTED,
        }
        else None
    )

    with pytest.raises(
        ValueError,
        match=(
            "terminal RecoveryEvent requires "
            "completed_at"
        ),
    ):
        make_event(
            status=status,
            completed_at=None,
            message=message,
        )


@pytest.mark.parametrize(
    "status",
    [
        RecoveryEventStatus.FAILED,
        RecoveryEventStatus.ABORTED,
    ],
)
def test_failure_event_requires_message(
    status: RecoveryEventStatus,
) -> None:
    """失敗・中断状態には理由が必要となる。"""

    with pytest.raises(
        ValueError,
        match=(
            "failed or aborted RecoveryEvent "
            "requires message"
        ),
    ):
        make_event(
            status=status,
            message=None,
        )


def test_event_rejects_invalid_source_type() -> None:
    """RecoverySource以外を拒否する。"""

    with pytest.raises(
        TypeError,
        match="source must be a RecoverySource",
    ):
        make_event(source="runtime")


def test_event_rejects_invalid_category_type() -> None:
    """RecoveryEventCategory以外を拒否する。"""

    with pytest.raises(
        TypeError,
        match=(
            "category must be a "
            "RecoveryEventCategory"
        ),
    ):
        make_event(category="restart")


def test_event_rejects_invalid_status_type() -> None:
    """RecoveryEventStatus以外を拒否する。"""

    with pytest.raises(
        TypeError,
        match=(
            "status must be a RecoveryEventStatus"
        ),
    ):
        make_event(status="succeeded")


def test_event_rejects_empty_metadata_key() -> None:
    """空のMetadataキーを拒否する。"""

    with pytest.raises(
        ValueError,
        match="metadata key must not be empty",
    ):
        make_event(
            metadata={
                "   ": "value",
            }
        )


def test_metadata_value_rejects_empty_key() -> None:
    """空の検索キーを拒否する。"""

    event = make_event()

    with pytest.raises(
        ValueError,
        match="key must not be empty",
    ):
        event.metadata_value("   ")