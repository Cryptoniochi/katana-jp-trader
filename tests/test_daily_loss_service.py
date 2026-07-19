"""DailyLossServiceのテスト。"""

from datetime import date, datetime, timezone

import pytest

from app.risk.daily_loss_models import (
    DailyLossPolicy,
    DailyLossReason,
    DailyLossSnapshot,
    DailyLossStatus,
)
from app.risk.daily_loss_service import DailyLossService


@pytest.fixture
def policy() -> DailyLossPolicy:
    """標準テスト用Policyを返す。"""

    return DailyLossPolicy(
        max_daily_loss=100_000.0,
        warning_ratio=0.8,
    )


@pytest.fixture
def service(
    policy: DailyLossPolicy,
) -> DailyLossService:
    """標準テスト用Serviceを返す。"""

    return DailyLossService(
        policy=policy,
    )


def make_snapshot(
    *,
    realized_pnl: float = 0.0,
    unrealized_pnl: float = 0.0,
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
) -> DailyLossSnapshot:
    """DailyLossSnapshotを生成する。"""

    return DailyLossSnapshot(
        trading_date=trading_date,
        realized_pnl=realized_pnl,
        unrealized_pnl=unrealized_pnl,
        manual_blocked=manual_blocked,
        evaluated_at=evaluated_at,
    )


def test_active_when_loss_is_below_warning_threshold(
    service: DailyLossService,
) -> None:
    """警告水準未満ならACTIVEを返す。"""

    evaluation = service.evaluate(
        make_snapshot(
            realized_pnl=-50_000.0,
        )
    )

    assert evaluation.status is DailyLossStatus.ACTIVE
    assert evaluation.reason is DailyLossReason.WITHIN_LIMIT
    assert evaluation.total_pnl == -50_000.0
    assert evaluation.total_loss == 50_000.0
    assert evaluation.remaining_loss_capacity == 50_000.0
    assert evaluation.allows_new_entries
    assert not evaluation.is_blocked


def test_warning_at_warning_threshold(
    service: DailyLossService,
) -> None:
    """警告水準ちょうどでWARNINGを返す。"""

    evaluation = service.evaluate(
        make_snapshot(
            realized_pnl=-80_000.0,
        )
    )

    assert evaluation.status is DailyLossStatus.WARNING
    assert (
        evaluation.reason
        is DailyLossReason.WARNING_THRESHOLD_REACHED
    )
    assert evaluation.total_loss == 80_000.0
    assert evaluation.remaining_loss_capacity == 20_000.0
    assert evaluation.allows_new_entries
    assert not evaluation.is_blocked


def test_warning_between_warning_and_limit(
    service: DailyLossService,
) -> None:
    """警告水準以上かつ最大損失未満ならWARNINGを返す。"""

    evaluation = service.evaluate(
        make_snapshot(
            realized_pnl=-90_000.0,
        )
    )

    assert evaluation.status is DailyLossStatus.WARNING
    assert (
        evaluation.reason
        is DailyLossReason.WARNING_THRESHOLD_REACHED
    )
    assert evaluation.total_loss == 90_000.0
    assert evaluation.remaining_loss_capacity == 10_000.0


def test_blocked_at_daily_loss_limit(
    service: DailyLossService,
) -> None:
    """最大日次損失ちょうどでBLOCKEDを返す。"""

    evaluation = service.evaluate(
        make_snapshot(
            realized_pnl=-100_000.0,
        )
    )

    assert evaluation.status is DailyLossStatus.BLOCKED
    assert (
        evaluation.reason
        is DailyLossReason.LOSS_LIMIT_REACHED
    )
    assert evaluation.total_loss == 100_000.0
    assert evaluation.remaining_loss_capacity == 0.0
    assert not evaluation.allows_new_entries
    assert evaluation.is_blocked


def test_blocked_above_daily_loss_limit(
    service: DailyLossService,
) -> None:
    """最大日次損失超過時にBLOCKEDを返す。"""

    evaluation = service.evaluate(
        make_snapshot(
            realized_pnl=-125_000.0,
        )
    )

    assert evaluation.status is DailyLossStatus.BLOCKED
    assert (
        evaluation.reason
        is DailyLossReason.LOSS_LIMIT_REACHED
    )
    assert evaluation.total_loss == 125_000.0
    assert evaluation.remaining_loss_capacity == 0.0


def test_manual_block_has_priority_over_loss_amount(
    service: DailyLossService,
) -> None:
    """損失がなくても手動停止中ならBLOCKEDを返す。"""

    evaluation = service.evaluate(
        make_snapshot(
            realized_pnl=20_000.0,
            manual_blocked=True,
        )
    )

    assert evaluation.status is DailyLossStatus.BLOCKED
    assert (
        evaluation.reason
        is DailyLossReason.MANUALLY_BLOCKED
    )
    assert evaluation.total_loss == 0.0
    assert evaluation.remaining_loss_capacity == 100_000.0
    assert not evaluation.allows_new_entries


def test_manual_block_reason_has_priority_when_limit_also_reached(
    service: DailyLossService,
) -> None:
    """最大損失到達時でも手動停止理由を優先する。"""

    evaluation = service.evaluate(
        make_snapshot(
            realized_pnl=-100_000.0,
            manual_blocked=True,
        )
    )

    assert evaluation.status is DailyLossStatus.BLOCKED
    assert (
        evaluation.reason
        is DailyLossReason.MANUALLY_BLOCKED
    )


def test_combines_realized_and_unrealized_pnl(
    service: DailyLossService,
) -> None:
    """実現損益と含み損益を合算して判定する。"""

    evaluation = service.evaluate(
        make_snapshot(
            realized_pnl=-50_000.0,
            unrealized_pnl=-35_000.0,
        )
    )

    assert evaluation.status is DailyLossStatus.WARNING
    assert evaluation.total_pnl == -85_000.0
    assert evaluation.total_loss == 85_000.0
    assert evaluation.remaining_loss_capacity == 15_000.0


def test_profit_offsets_loss(
    service: DailyLossService,
) -> None:
    """利益が損失を相殺する。"""

    evaluation = service.evaluate(
        make_snapshot(
            realized_pnl=-90_000.0,
            unrealized_pnl=30_000.0,
        )
    )

    assert evaluation.status is DailyLossStatus.ACTIVE
    assert evaluation.total_pnl == -60_000.0
    assert evaluation.total_loss == 60_000.0
    assert evaluation.remaining_loss_capacity == 40_000.0


def test_positive_total_pnl_has_zero_total_loss(
    service: DailyLossService,
) -> None:
    """合計損益が利益なら損失額を0とする。"""

    evaluation = service.evaluate(
        make_snapshot(
            realized_pnl=50_000.0,
            unrealized_pnl=-10_000.0,
        )
    )

    assert evaluation.status is DailyLossStatus.ACTIVE
    assert evaluation.total_pnl == 40_000.0
    assert evaluation.total_loss == 0.0
    assert evaluation.remaining_loss_capacity == 100_000.0


def test_zero_pnl_is_active(
    service: DailyLossService,
) -> None:
    """損益0ならACTIVEを返す。"""

    evaluation = service.evaluate(
        make_snapshot()
    )

    assert evaluation.status is DailyLossStatus.ACTIVE
    assert evaluation.reason is DailyLossReason.WITHIN_LIMIT
    assert evaluation.total_loss == 0.0
    assert evaluation.remaining_loss_capacity == 100_000.0


def test_allows_new_entries_helper(
    service: DailyLossService,
) -> None:
    """新規エントリー可否の補助メソッドを検証する。"""

    assert service.allows_new_entries(
        make_snapshot(
            realized_pnl=-99_999.0,
        )
    )

    assert not service.allows_new_entries(
        make_snapshot(
            realized_pnl=-100_000.0,
        )
    )


def test_is_blocked_helper(
    service: DailyLossService,
) -> None:
    """停止状態判定の補助メソッドを検証する。"""

    assert not service.is_blocked(
        make_snapshot(
            realized_pnl=-80_000.0,
        )
    )

    assert service.is_blocked(
        make_snapshot(
            realized_pnl=-100_000.0,
        )
    )


def test_preserves_snapshot_date_and_time(
    service: DailyLossService,
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
    service: DailyLossService,
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


def test_metadata_contains_policy_and_manual_block_state(
    service: DailyLossService,
) -> None:
    """判定メタデータにPolicyと手動停止状態を含める。"""

    evaluation = service.evaluate(
        make_snapshot(
            manual_blocked=True,
        )
    )

    assert evaluation.metadata == {
        "manual_blocked": True,
        "warning_ratio": 0.8,
    }


@pytest.mark.parametrize(
    "max_daily_loss",
    (
        0.0,
        -1.0,
    ),
)
def test_policy_rejects_non_positive_max_daily_loss(
    max_daily_loss: float,
) -> None:
    """0以下の最大日次損失額を拒否する。"""

    with pytest.raises(
        ValueError,
        match="max_daily_lossは0より大きい必要があります。",
    ):
        DailyLossPolicy(
            max_daily_loss=max_daily_loss,
        )


@pytest.mark.parametrize(
    "max_daily_loss",
    (
        float("nan"),
        float("inf"),
        float("-inf"),
    ),
)
def test_policy_rejects_non_finite_max_daily_loss(
    max_daily_loss: float,
) -> None:
    """非有限の最大日次損失額を拒否する。"""

    with pytest.raises(
        ValueError,
        match="max_daily_lossは有限の数値である必要があります。",
    ):
        DailyLossPolicy(
            max_daily_loss=max_daily_loss,
        )


@pytest.mark.parametrize(
    "warning_ratio",
    (
        0.0,
        1.0,
        -0.1,
        1.1,
    ),
)
def test_policy_rejects_out_of_range_warning_ratio(
    warning_ratio: float,
) -> None:
    """範囲外の警告比率を拒否する。"""

    with pytest.raises(
        ValueError,
        match="warning_ratioは0より大きく1未満である必要があります。",
    ):
        DailyLossPolicy(
            max_daily_loss=100_000.0,
            warning_ratio=warning_ratio,
        )


@pytest.mark.parametrize(
    "warning_ratio",
    (
        float("nan"),
        float("inf"),
        float("-inf"),
    ),
)
def test_policy_rejects_non_finite_warning_ratio(
    warning_ratio: float,
) -> None:
    """非有限の警告比率を拒否する。"""

    with pytest.raises(
        ValueError,
        match="warning_ratioは有限の数値である必要があります。",
    ):
        DailyLossPolicy(
            max_daily_loss=100_000.0,
            warning_ratio=warning_ratio,
        )


@pytest.mark.parametrize(
    ("field_name", "value"),
    (
        ("realized_pnl", float("nan")),
        ("realized_pnl", float("inf")),
        ("unrealized_pnl", float("nan")),
        ("unrealized_pnl", float("-inf")),
    ),
)
def test_snapshot_rejects_non_finite_pnl(
    field_name: str,
    value: float,
) -> None:
    """Snapshotの非有限損益を拒否する。"""

    arguments = {
        "realized_pnl": 0.0,
        "unrealized_pnl": 0.0,
    }
    arguments[field_name] = value

    with pytest.raises(
        ValueError,
        match=rf"{field_name}は有限の数値である必要があります。",
    ):
        make_snapshot(
            **arguments,
        )
