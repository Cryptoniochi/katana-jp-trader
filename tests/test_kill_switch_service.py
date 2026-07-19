"""KillSwitchServiceのテスト。"""

from datetime import datetime, timezone

import pytest

from app.risk.kill_switch_models import (
    KillSwitchReason,
    KillSwitchSnapshot,
    KillSwitchStatus,
)
from app.risk.kill_switch_service import KillSwitchService


@pytest.fixture
def service() -> KillSwitchService:
    """テスト用Serviceを返す。"""

    return KillSwitchService()


def make_snapshot(
    *,
    manual_blocked: bool = False,
    daily_loss_blocked: bool = False,
    consecutive_loss_blocked: bool = False,
    runtime_health_ok: bool = True,
    heartbeat_alive: bool = True,
    broker_available: bool = True,
    evaluated_at: datetime = datetime(
        2026,
        7,
        19,
        0,
        0,
        tzinfo=timezone.utc,
    ),
) -> KillSwitchSnapshot:
    """KillSwitchSnapshotを生成する。"""

    return KillSwitchSnapshot(
        manual_blocked=manual_blocked,
        daily_loss_blocked=daily_loss_blocked,
        consecutive_loss_blocked=consecutive_loss_blocked,
        runtime_health_ok=runtime_health_ok,
        heartbeat_alive=heartbeat_alive,
        broker_available=broker_available,
        evaluated_at=evaluated_at,
    )


def test_active_when_all_conditions_are_healthy(
    service: KillSwitchService,
) -> None:
    """すべて正常ならACTIVEを返す。"""

    evaluation = service.evaluate(
        make_snapshot()
    )

    assert evaluation.status is KillSwitchStatus.ACTIVE
    assert evaluation.reason is KillSwitchReason.NONE
    assert evaluation.allows_new_entries
    assert not evaluation.is_blocked


def test_blocks_when_manually_blocked(
    service: KillSwitchService,
) -> None:
    """手動停止中ならBLOCKEDを返す。"""

    evaluation = service.evaluate(
        make_snapshot(
            manual_blocked=True,
        )
    )

    assert evaluation.status is KillSwitchStatus.BLOCKED
    assert evaluation.reason is KillSwitchReason.MANUAL
    assert not evaluation.allows_new_entries
    assert evaluation.is_blocked


def test_blocks_for_daily_loss(
    service: KillSwitchService,
) -> None:
    """日次損失制限でBLOCKEDを返す。"""

    evaluation = service.evaluate(
        make_snapshot(
            daily_loss_blocked=True,
        )
    )

    assert evaluation.status is KillSwitchStatus.BLOCKED
    assert evaluation.reason is KillSwitchReason.DAILY_LOSS


def test_blocks_for_consecutive_loss(
    service: KillSwitchService,
) -> None:
    """連敗制限でBLOCKEDを返す。"""

    evaluation = service.evaluate(
        make_snapshot(
            consecutive_loss_blocked=True,
        )
    )

    assert evaluation.status is KillSwitchStatus.BLOCKED
    assert evaluation.reason is KillSwitchReason.CONSECUTIVE_LOSS


def test_blocks_for_runtime_health_error(
    service: KillSwitchService,
) -> None:
    """Runtime Health異常でBLOCKEDを返す。"""

    evaluation = service.evaluate(
        make_snapshot(
            runtime_health_ok=False,
        )
    )

    assert evaluation.status is KillSwitchStatus.BLOCKED
    assert evaluation.reason is KillSwitchReason.RUNTIME_HEALTH


def test_blocks_for_stale_heartbeat(
    service: KillSwitchService,
) -> None:
    """Heartbeat停止でBLOCKEDを返す。"""

    evaluation = service.evaluate(
        make_snapshot(
            heartbeat_alive=False,
        )
    )

    assert evaluation.status is KillSwitchStatus.BLOCKED
    assert evaluation.reason is KillSwitchReason.HEARTBEAT


def test_blocks_when_broker_is_unavailable(
    service: KillSwitchService,
) -> None:
    """Broker利用不可でBLOCKEDを返す。"""

    evaluation = service.evaluate(
        make_snapshot(
            broker_available=False,
        )
    )

    assert evaluation.status is KillSwitchStatus.BLOCKED
    assert evaluation.reason is KillSwitchReason.BROKER


@pytest.mark.parametrize(
    (
        "snapshot",
        "expected_reason",
    ),
    (
        (
            make_snapshot(
                manual_blocked=True,
                daily_loss_blocked=True,
                consecutive_loss_blocked=True,
                runtime_health_ok=False,
                heartbeat_alive=False,
                broker_available=False,
            ),
            KillSwitchReason.MANUAL,
        ),
        (
            make_snapshot(
                daily_loss_blocked=True,
                consecutive_loss_blocked=True,
                runtime_health_ok=False,
                heartbeat_alive=False,
                broker_available=False,
            ),
            KillSwitchReason.DAILY_LOSS,
        ),
        (
            make_snapshot(
                consecutive_loss_blocked=True,
                runtime_health_ok=False,
                heartbeat_alive=False,
                broker_available=False,
            ),
            KillSwitchReason.CONSECUTIVE_LOSS,
        ),
        (
            make_snapshot(
                runtime_health_ok=False,
                heartbeat_alive=False,
                broker_available=False,
            ),
            KillSwitchReason.RUNTIME_HEALTH,
        ),
        (
            make_snapshot(
                heartbeat_alive=False,
                broker_available=False,
            ),
            KillSwitchReason.HEARTBEAT,
        ),
    ),
)
def test_block_reason_priority(
    service: KillSwitchService,
    snapshot: KillSwitchSnapshot,
    expected_reason: KillSwitchReason,
) -> None:
    """複数異常時に定義済み優先順位を適用する。"""

    evaluation = service.evaluate(snapshot)

    assert evaluation.status is KillSwitchStatus.BLOCKED
    assert evaluation.reason is expected_reason


def test_allows_new_entries_helper(
    service: KillSwitchService,
) -> None:
    """新規エントリー可否の補助メソッドを検証する。"""

    assert service.allows_new_entries(
        make_snapshot()
    )

    assert not service.allows_new_entries(
        make_snapshot(
            daily_loss_blocked=True,
        )
    )


def test_is_blocked_helper(
    service: KillSwitchService,
) -> None:
    """停止状態判定の補助メソッドを検証する。"""

    assert not service.is_blocked(
        make_snapshot()
    )

    assert service.is_blocked(
        make_snapshot(
            runtime_health_ok=False,
        )
    )


def test_preserves_evaluated_at(
    service: KillSwitchService,
) -> None:
    """Snapshotの評価時刻を結果へ引き継ぐ。"""

    evaluated_at = datetime(
        2026,
        7,
        20,
        9,
        15,
        tzinfo=timezone.utc,
    )

    evaluation = service.evaluate(
        make_snapshot(
            evaluated_at=evaluated_at,
        )
    )

    assert evaluation.evaluated_at == evaluated_at


def test_normalizes_naive_evaluated_at_to_utc(
    service: KillSwitchService,
) -> None:
    """タイムゾーンなし時刻をUTCとして扱う。"""

    evaluation = service.evaluate(
        make_snapshot(
            evaluated_at=datetime(
                2026,
                7,
                19,
                9,
                0,
            ),
        )
    )

    assert evaluation.evaluated_at.tzinfo is timezone.utc


def test_metadata_contains_all_input_flags(
    service: KillSwitchService,
) -> None:
    """判定メタデータにすべての入力状態を含める。"""

    evaluation = service.evaluate(
        make_snapshot(
            manual_blocked=True,
            daily_loss_blocked=True,
            consecutive_loss_blocked=True,
            runtime_health_ok=False,
            heartbeat_alive=False,
            broker_available=False,
        )
    )

    assert evaluation.metadata == {
        "manual_blocked": True,
        "daily_loss_blocked": True,
        "consecutive_loss_blocked": True,
        "runtime_health_ok": False,
        "heartbeat_alive": False,
        "broker_available": False,
    }


@pytest.mark.parametrize(
    (
        "field_name",
        "field_value",
        "expected_reason",
    ),
    (
        (
            "manual_blocked",
            True,
            KillSwitchReason.MANUAL,
        ),
        (
            "daily_loss_blocked",
            True,
            KillSwitchReason.DAILY_LOSS,
        ),
        (
            "consecutive_loss_blocked",
            True,
            KillSwitchReason.CONSECUTIVE_LOSS,
        ),
        (
            "runtime_health_ok",
            False,
            KillSwitchReason.RUNTIME_HEALTH,
        ),
        (
            "heartbeat_alive",
            False,
            KillSwitchReason.HEARTBEAT,
        ),
        (
            "broker_available",
            False,
            KillSwitchReason.BROKER,
        ),
    ),
)
def test_each_single_failure_condition_blocks(
    service: KillSwitchService,
    field_name: str,
    field_value: bool,
    expected_reason: KillSwitchReason,
) -> None:
    """各異常条件が単独でも停止を発生させる。"""

    arguments = {
        "manual_blocked": False,
        "daily_loss_blocked": False,
        "consecutive_loss_blocked": False,
        "runtime_health_ok": True,
        "heartbeat_alive": True,
        "broker_available": True,
    }
    arguments[field_name] = field_value

    evaluation = service.evaluate(
        make_snapshot(
            **arguments,
        )
    )

    assert evaluation.status is KillSwitchStatus.BLOCKED
    assert evaluation.reason is expected_reason
