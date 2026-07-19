"""ConsecutiveLossServiceのテスト。"""

from datetime import date, datetime, timezone

import pytest

from app.risk.consecutive_loss_models import (
    ConsecutiveLossPolicy,
    ConsecutiveLossReason,
    ConsecutiveLossSnapshot,
    ConsecutiveLossStatus,
)
from app.risk.consecutive_loss_service import ConsecutiveLossService


@pytest.fixture
def policy() -> ConsecutiveLossPolicy:
    """標準テスト用Policyを返す。"""

    return ConsecutiveLossPolicy(
        max_consecutive_losses=3,
        warning_consecutive_losses=2,
    )


@pytest.fixture
def service(
    policy: ConsecutiveLossPolicy,
) -> ConsecutiveLossService:
    """標準テスト用Serviceを返す。"""

    return ConsecutiveLossService(
        policy=policy,
    )


def make_snapshot(
    *,
    consecutive_losses: int = 0,
    last_trade_pnl: float | None = None,
    manual_blocked: bool = False,
    trading_date: date = date(2026, 7, 19),
    evaluated_at: datetime = datetime(
        2026,
        7,
        19,
        0,
        0,
        tzinfo=timezone.utc,
    ),
) -> ConsecutiveLossSnapshot:
    """ConsecutiveLossSnapshotを生成する。"""

    return ConsecutiveLossSnapshot(
        trading_date=trading_date,
        consecutive_losses=consecutive_losses,
        last_trade_pnl=last_trade_pnl,
        manual_blocked=manual_blocked,
        evaluated_at=evaluated_at,
    )


def test_active_when_below_warning_threshold(
    service: ConsecutiveLossService,
) -> None:
    """警告連敗数未満ならACTIVEを返す。"""

    evaluation = service.evaluate(
        make_snapshot(
            consecutive_losses=1,
            last_trade_pnl=-10_000.0,
        )
    )

    assert evaluation.status is ConsecutiveLossStatus.ACTIVE
    assert evaluation.reason is ConsecutiveLossReason.WITHIN_LIMIT
    assert evaluation.consecutive_losses == 1
    assert evaluation.remaining_losses_before_block == 2
    assert evaluation.allows_new_entries
    assert not evaluation.is_blocked


def test_warning_at_warning_threshold(
    service: ConsecutiveLossService,
) -> None:
    """警告連敗数ちょうどでWARNINGを返す。"""

    evaluation = service.evaluate(
        make_snapshot(
            consecutive_losses=2,
            last_trade_pnl=-20_000.0,
        )
    )

    assert evaluation.status is ConsecutiveLossStatus.WARNING
    assert (
        evaluation.reason
        is ConsecutiveLossReason.WARNING_THRESHOLD_REACHED
    )
    assert evaluation.remaining_losses_before_block == 1
    assert evaluation.allows_new_entries
    assert not evaluation.is_blocked


def test_blocked_at_maximum_consecutive_losses(
    service: ConsecutiveLossService,
) -> None:
    """最大連敗数ちょうどでBLOCKEDを返す。"""

    evaluation = service.evaluate(
        make_snapshot(
            consecutive_losses=3,
            last_trade_pnl=-30_000.0,
        )
    )

    assert evaluation.status is ConsecutiveLossStatus.BLOCKED
    assert (
        evaluation.reason
        is ConsecutiveLossReason.LOSS_LIMIT_REACHED
    )
    assert evaluation.remaining_losses_before_block == 0
    assert not evaluation.allows_new_entries
    assert evaluation.is_blocked


def test_blocked_above_maximum_consecutive_losses(
    service: ConsecutiveLossService,
) -> None:
    """最大連敗数超過時もBLOCKEDを返す。"""

    evaluation = service.evaluate(
        make_snapshot(
            consecutive_losses=5,
        )
    )

    assert evaluation.status is ConsecutiveLossStatus.BLOCKED
    assert (
        evaluation.reason
        is ConsecutiveLossReason.LOSS_LIMIT_REACHED
    )
    assert evaluation.remaining_losses_before_block == 0


def test_manual_block_has_priority(
    service: ConsecutiveLossService,
) -> None:
    """連敗数が0でも手動停止中ならBLOCKEDを返す。"""

    evaluation = service.evaluate(
        make_snapshot(
            consecutive_losses=0,
            manual_blocked=True,
        )
    )

    assert evaluation.status is ConsecutiveLossStatus.BLOCKED
    assert (
        evaluation.reason
        is ConsecutiveLossReason.MANUALLY_BLOCKED
    )
    assert evaluation.remaining_losses_before_block == 3
    assert not evaluation.allows_new_entries


def test_manual_block_reason_has_priority_when_limit_reached(
    service: ConsecutiveLossService,
) -> None:
    """最大連敗数到達時でも手動停止理由を優先する。"""

    evaluation = service.evaluate(
        make_snapshot(
            consecutive_losses=3,
            manual_blocked=True,
        )
    )

    assert evaluation.status is ConsecutiveLossStatus.BLOCKED
    assert (
        evaluation.reason
        is ConsecutiveLossReason.MANUALLY_BLOCKED
    )


def test_zero_losses_is_active(
    service: ConsecutiveLossService,
) -> None:
    """連敗数0ならACTIVEを返す。"""

    evaluation = service.evaluate(
        make_snapshot()
    )

    assert evaluation.status is ConsecutiveLossStatus.ACTIVE
    assert evaluation.reason is ConsecutiveLossReason.WITHIN_LIMIT
    assert evaluation.remaining_losses_before_block == 3


def test_preserves_last_trade_pnl(
    service: ConsecutiveLossService,
) -> None:
    """直近取引損益を判定結果へ引き継ぐ。"""

    evaluation = service.evaluate(
        make_snapshot(
            consecutive_losses=1,
            last_trade_pnl=-12_345.0,
        )
    )

    assert evaluation.last_trade_pnl == -12_345.0


def test_allows_none_last_trade_pnl(
    service: ConsecutiveLossService,
) -> None:
    """直近取引がない状態を許可する。"""

    evaluation = service.evaluate(
        make_snapshot(
            last_trade_pnl=None,
        )
    )

    assert evaluation.last_trade_pnl is None


def test_allows_new_entries_helper(
    service: ConsecutiveLossService,
) -> None:
    """新規エントリー可否の補助メソッドを検証する。"""

    assert service.allows_new_entries(
        make_snapshot(
            consecutive_losses=2,
        )
    )

    assert not service.allows_new_entries(
        make_snapshot(
            consecutive_losses=3,
        )
    )


def test_is_blocked_helper(
    service: ConsecutiveLossService,
) -> None:
    """停止状態判定の補助メソッドを検証する。"""

    assert not service.is_blocked(
        make_snapshot(
            consecutive_losses=2,
        )
    )

    assert service.is_blocked(
        make_snapshot(
            consecutive_losses=3,
        )
    )


def test_preserves_snapshot_date_and_time(
    service: ConsecutiveLossService,
) -> None:
    """Snapshotの取引日と評価時刻を結果へ引き継ぐ。"""

    trading_date = date(2026, 7, 20)
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
            trading_date=trading_date,
            evaluated_at=evaluated_at,
        )
    )

    assert evaluation.trading_date == trading_date
    assert evaluation.evaluated_at == evaluated_at


def test_normalizes_naive_evaluated_at_to_utc(
    service: ConsecutiveLossService,
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


def test_metadata_contains_manual_block_state(
    service: ConsecutiveLossService,
) -> None:
    """判定メタデータに手動停止状態を含める。"""

    evaluation = service.evaluate(
        make_snapshot(
            manual_blocked=True,
        )
    )

    assert evaluation.metadata == {
        "manual_blocked": True,
    }


def test_policy_sets_default_warning_to_one_before_limit() -> None:
    """警告値未指定時は最大連敗数の1つ前を使用する。"""

    policy = ConsecutiveLossPolicy(
        max_consecutive_losses=5,
    )

    assert policy.warning_consecutive_losses == 4


def test_policy_sets_minimum_default_warning_to_one() -> None:
    """最大連敗数1の場合も警告値の下限を1とする。"""

    with pytest.raises(
        ValueError,
        match=(
            "warning_consecutive_lossesは"
            "max_consecutive_losses未満である必要があります。"
        ),
    ):
        ConsecutiveLossPolicy(
            max_consecutive_losses=1,
        )


@pytest.mark.parametrize(
    "max_consecutive_losses",
    (
        0,
        -1,
    ),
)
def test_policy_rejects_non_positive_maximum(
    max_consecutive_losses: int,
) -> None:
    """0以下の最大連敗数を拒否する。"""

    with pytest.raises(
        ValueError,
        match=(
            "max_consecutive_lossesは"
            "1以上である必要があります。"
        ),
    ):
        ConsecutiveLossPolicy(
            max_consecutive_losses=max_consecutive_losses,
        )


@pytest.mark.parametrize(
    "warning_consecutive_losses",
    (
        0,
        -1,
    ),
)
def test_policy_rejects_non_positive_warning(
    warning_consecutive_losses: int,
) -> None:
    """0以下の警告連敗数を拒否する。"""

    with pytest.raises(
        ValueError,
        match=(
            "warning_consecutive_lossesは"
            "1以上である必要があります。"
        ),
    ):
        ConsecutiveLossPolicy(
            max_consecutive_losses=3,
            warning_consecutive_losses=warning_consecutive_losses,
        )


@pytest.mark.parametrize(
    "warning_consecutive_losses",
    (
        3,
        4,
    ),
)
def test_policy_rejects_warning_at_or_above_maximum(
    warning_consecutive_losses: int,
) -> None:
    """最大連敗数以上の警告値を拒否する。"""

    with pytest.raises(
        ValueError,
        match=(
            "warning_consecutive_lossesは"
            "max_consecutive_losses未満である必要があります。"
        ),
    ):
        ConsecutiveLossPolicy(
            max_consecutive_losses=3,
            warning_consecutive_losses=warning_consecutive_losses,
        )


def test_snapshot_rejects_negative_consecutive_losses() -> None:
    """負の連敗数を拒否する。"""

    with pytest.raises(
        ValueError,
        match="consecutive_lossesは0以上である必要があります。",
    ):
        make_snapshot(
            consecutive_losses=-1,
        )


@pytest.mark.parametrize(
    "last_trade_pnl",
    (
        float("nan"),
        float("inf"),
        float("-inf"),
    ),
)
def test_snapshot_rejects_non_finite_last_trade_pnl(
    last_trade_pnl: float,
) -> None:
    """非有限の直近取引損益を拒否する。"""

    with pytest.raises(
        ValueError,
        match="last_trade_pnlは有限の数値である必要があります。",
    ):
        make_snapshot(
            last_trade_pnl=last_trade_pnl,
        )


def test_custom_policy_boundaries() -> None:
    """任意の警告値と最大値で判定できる。"""

    service = ConsecutiveLossService(
        policy=ConsecutiveLossPolicy(
            max_consecutive_losses=5,
            warning_consecutive_losses=3,
        )
    )

    active = service.evaluate(
        make_snapshot(
            consecutive_losses=2,
        )
    )
    warning = service.evaluate(
        make_snapshot(
            consecutive_losses=3,
        )
    )
    blocked = service.evaluate(
        make_snapshot(
            consecutive_losses=5,
        )
    )

    assert active.status is ConsecutiveLossStatus.ACTIVE
    assert warning.status is ConsecutiveLossStatus.WARNING
    assert blocked.status is ConsecutiveLossStatus.BLOCKED
