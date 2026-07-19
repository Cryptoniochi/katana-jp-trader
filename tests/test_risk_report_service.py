"""RiskReportServiceのテスト。"""

from datetime import date, datetime, timezone

import pytest

from app.risk.risk_report_models import (
    RiskReportItem,
    RiskReportReason,
    RiskReportSnapshot,
    RiskReportStatus,
)
from app.risk.risk_report_service import RiskReportService


@pytest.fixture
def service() -> RiskReportService:
    """テスト用Serviceを返す。"""

    return RiskReportService()


def make_item(
    *,
    name: str,
    status: RiskReportStatus,
    reason: RiskReportReason,
    message: str,
    blocks_new_entries: bool,
    metadata: dict[str, object] | None = None,
) -> RiskReportItem:
    """RiskReportItemを生成する。"""

    return RiskReportItem(
        name=name,
        status=status,
        reason=reason,
        message=message,
        blocks_new_entries=blocks_new_entries,
        metadata=metadata,
    )


def clear_item(
    name: str = "position_sizing",
) -> RiskReportItem:
    """正常なRiskReportItemを返す。"""

    return make_item(
        name=name,
        status=RiskReportStatus.CLEAR,
        reason=RiskReportReason.ALL_CLEAR,
        message="リスク制約内です。",
        blocks_new_entries=False,
    )


def warning_item(
    *,
    name: str = "daily_loss",
    reason: RiskReportReason = RiskReportReason.DAILY_LOSS_WARNING,
) -> RiskReportItem:
    """警告状態のRiskReportItemを返す。"""

    return make_item(
        name=name,
        status=RiskReportStatus.WARNING,
        reason=reason,
        message="警告水準に到達しています。",
        blocks_new_entries=False,
    )


def blocked_item(
    *,
    name: str = "kill_switch",
    reason: RiskReportReason = RiskReportReason.KILL_SWITCH_BLOCKED,
) -> RiskReportItem:
    """停止状態のRiskReportItemを返す。"""

    return make_item(
        name=name,
        status=RiskReportStatus.BLOCKED,
        reason=reason,
        message="新規エントリーを停止しています。",
        blocks_new_entries=True,
    )


def make_snapshot(
    *,
    items: tuple[RiskReportItem, ...],
    trading_date: date = date(2026, 7, 19),
    generated_at: datetime = datetime(
        2026,
        7,
        19,
        0,
        0,
        tzinfo=timezone.utc,
    ),
    metadata: dict[str, object] | None = None,
) -> RiskReportSnapshot:
    """RiskReportSnapshotを生成する。"""

    return RiskReportSnapshot(
        trading_date=trading_date,
        items=items,
        generated_at=generated_at,
        metadata=metadata,
    )


def test_generates_clear_report_when_all_items_are_clear(
    service: RiskReportService,
) -> None:
    """すべて正常ならCLEARを返す。"""

    report = service.generate(
        make_snapshot(
            items=(
                clear_item("position_sizing"),
                clear_item("daily_loss"),
                clear_item("consecutive_loss"),
                clear_item("kill_switch"),
            ),
        )
    )

    assert report.status is RiskReportStatus.CLEAR
    assert report.primary_reason is RiskReportReason.ALL_CLEAR
    assert report.warning_reasons == ()
    assert report.blocking_reasons == ()
    assert report.allows_new_entries
    assert not report.is_blocked
    assert not report.has_warning


def test_generates_warning_report_when_warning_exists(
    service: RiskReportService,
) -> None:
    """停止項目がなく警告項目があればWARNINGを返す。"""

    report = service.generate(
        make_snapshot(
            items=(
                clear_item(),
                warning_item(),
            ),
        )
    )

    assert report.status is RiskReportStatus.WARNING
    assert (
        report.primary_reason
        is RiskReportReason.DAILY_LOSS_WARNING
    )
    assert report.warning_reasons == (
        RiskReportReason.DAILY_LOSS_WARNING,
    )
    assert report.blocking_reasons == ()
    assert report.allows_new_entries
    assert not report.is_blocked
    assert report.has_warning


def test_generates_blocked_report_when_blocked_item_exists(
    service: RiskReportService,
) -> None:
    """停止項目があればBLOCKEDを返す。"""

    report = service.generate(
        make_snapshot(
            items=(
                clear_item(),
                blocked_item(),
            ),
        )
    )

    assert report.status is RiskReportStatus.BLOCKED
    assert (
        report.primary_reason
        is RiskReportReason.KILL_SWITCH_BLOCKED
    )
    assert report.warning_reasons == ()
    assert report.blocking_reasons == (
        RiskReportReason.KILL_SWITCH_BLOCKED,
    )
    assert not report.allows_new_entries
    assert report.is_blocked
    assert report.has_warning


def test_blocked_takes_priority_over_warning(
    service: RiskReportService,
) -> None:
    """警告と停止が混在する場合はBLOCKEDを優先する。"""

    report = service.generate(
        make_snapshot(
            items=(
                warning_item(),
                blocked_item(),
            ),
        )
    )

    assert report.status is RiskReportStatus.BLOCKED
    assert (
        report.primary_reason
        is RiskReportReason.KILL_SWITCH_BLOCKED
    )
    assert report.warning_reasons == (
        RiskReportReason.DAILY_LOSS_WARNING,
    )
    assert report.blocking_reasons == (
        RiskReportReason.KILL_SWITCH_BLOCKED,
    )


def test_uses_first_warning_as_primary_reason(
    service: RiskReportService,
) -> None:
    """最初の警告理由をprimary_reasonとして使用する。"""

    report = service.generate(
        make_snapshot(
            items=(
                warning_item(
                    name="position_sizing",
                    reason=(
                        RiskReportReason.POSITION_SIZE_REDUCED
                    ),
                ),
                warning_item(
                    name="daily_loss",
                    reason=RiskReportReason.DAILY_LOSS_WARNING,
                ),
            ),
        )
    )

    assert report.status is RiskReportStatus.WARNING
    assert (
        report.primary_reason
        is RiskReportReason.POSITION_SIZE_REDUCED
    )
    assert report.warning_reasons == (
        RiskReportReason.POSITION_SIZE_REDUCED,
        RiskReportReason.DAILY_LOSS_WARNING,
    )


def test_uses_first_blocking_reason_as_primary_reason(
    service: RiskReportService,
) -> None:
    """最初の停止理由をprimary_reasonとして使用する。"""

    report = service.generate(
        make_snapshot(
            items=(
                blocked_item(
                    name="daily_loss",
                    reason=RiskReportReason.DAILY_LOSS_BLOCKED,
                ),
                blocked_item(
                    name="kill_switch",
                    reason=RiskReportReason.KILL_SWITCH_BLOCKED,
                ),
            ),
        )
    )

    assert report.status is RiskReportStatus.BLOCKED
    assert (
        report.primary_reason
        is RiskReportReason.DAILY_LOSS_BLOCKED
    )
    assert report.blocking_reasons == (
        RiskReportReason.DAILY_LOSS_BLOCKED,
        RiskReportReason.KILL_SWITCH_BLOCKED,
    )


def test_preserves_items_order(
    service: RiskReportService,
) -> None:
    """入力された項目順を維持する。"""

    items = (
        clear_item("position_sizing"),
        warning_item(name="daily_loss"),
        blocked_item(name="kill_switch"),
    )

    report = service.generate(
        make_snapshot(
            items=items,
        )
    )

    assert report.items == items


def test_preserves_snapshot_date_time_and_metadata(
    service: RiskReportService,
) -> None:
    """Snapshotの日付、生成時刻、metadataを引き継ぐ。"""

    trading_date = date(2026, 7, 20)
    generated_at = datetime(
        2026,
        7,
        20,
        9,
        15,
        tzinfo=timezone.utc,
    )
    metadata = {
        "runtime_id": "runtime-001",
        "cycle": 10,
    }

    report = service.generate(
        make_snapshot(
            items=(clear_item(),),
            trading_date=trading_date,
            generated_at=generated_at,
            metadata=metadata,
        )
    )

    assert report.trading_date == trading_date
    assert report.generated_at == generated_at
    assert report.metadata == metadata


def test_normalizes_naive_generated_at_to_utc(
    service: RiskReportService,
) -> None:
    """タイムゾーンなし生成時刻をUTCとして扱う。"""

    report = service.generate(
        make_snapshot(
            items=(clear_item(),),
            generated_at=datetime(
                2026,
                7,
                19,
                9,
                0,
            ),
        )
    )

    assert report.generated_at.tzinfo is timezone.utc


def test_allows_new_entries_helper(
    service: RiskReportService,
) -> None:
    """新規エントリー可否の補助メソッドを検証する。"""

    assert service.allows_new_entries(
        make_snapshot(
            items=(warning_item(),),
        )
    )

    assert not service.allows_new_entries(
        make_snapshot(
            items=(blocked_item(),),
        )
    )


def test_is_blocked_helper(
    service: RiskReportService,
) -> None:
    """停止状態判定の補助メソッドを検証する。"""

    assert not service.is_blocked(
        make_snapshot(
            items=(clear_item(),),
        )
    )

    assert service.is_blocked(
        make_snapshot(
            items=(blocked_item(),),
        )
    )


def test_has_warning_helper(
    service: RiskReportService,
) -> None:
    """警告状態判定の補助メソッドを検証する。"""

    assert not service.has_warning(
        make_snapshot(
            items=(clear_item(),),
        )
    )

    assert service.has_warning(
        make_snapshot(
            items=(warning_item(),),
        )
    )

    assert service.has_warning(
        make_snapshot(
            items=(blocked_item(),),
        )
    )


def test_snapshot_rejects_empty_items() -> None:
    """空の項目一覧を拒否する。"""

    with pytest.raises(
        ValueError,
        match="itemsを1件以上指定してください。",
    ):
        make_snapshot(
            items=(),
        )


def test_snapshot_rejects_duplicate_item_names() -> None:
    """同じnameを持つ複数項目を拒否する。"""

    with pytest.raises(
        ValueError,
        match="RiskReportItemのnameは重複できません。",
    ):
        make_snapshot(
            items=(
                clear_item("daily_loss"),
                warning_item(name="daily_loss"),
            ),
        )


@pytest.mark.parametrize(
    "name",
    (
        "",
        "   ",
    ),
)
def test_item_rejects_blank_name(
    name: str,
) -> None:
    """空白のみのnameを拒否する。"""

    with pytest.raises(
        ValueError,
        match="nameを指定してください。",
    ):
        make_item(
            name=name,
            status=RiskReportStatus.CLEAR,
            reason=RiskReportReason.ALL_CLEAR,
            message="正常です。",
            blocks_new_entries=False,
        )


@pytest.mark.parametrize(
    "message",
    (
        "",
        "   ",
    ),
)
def test_item_rejects_blank_message(
    message: str,
) -> None:
    """空白のみのmessageを拒否する。"""

    with pytest.raises(
        ValueError,
        match="messageを指定してください。",
    ):
        make_item(
            name="daily_loss",
            status=RiskReportStatus.CLEAR,
            reason=RiskReportReason.ALL_CLEAR,
            message=message,
            blocks_new_entries=False,
        )


def test_item_strips_name_and_message() -> None:
    """nameとmessageの前後空白を除去する。"""

    item = make_item(
        name="  daily_loss  ",
        status=RiskReportStatus.CLEAR,
        reason=RiskReportReason.ALL_CLEAR,
        message="  正常です。  ",
        blocks_new_entries=False,
    )

    assert item.name == "daily_loss"
    assert item.message == "正常です。"


def test_item_rejects_block_flag_for_non_blocked_status() -> None:
    """BLOCKED以外でblocks_new_entries=Trueを拒否する。"""

    with pytest.raises(
        ValueError,
        match=(
            "blocks_new_entries=Trueの場合、"
            "statusはBLOCKEDである必要があります。"
        ),
    ):
        make_item(
            name="daily_loss",
            status=RiskReportStatus.WARNING,
            reason=RiskReportReason.DAILY_LOSS_WARNING,
            message="警告です。",
            blocks_new_entries=True,
        )


def test_item_requires_block_flag_for_blocked_status() -> None:
    """BLOCKED項目にはblocks_new_entries=Trueを要求する。"""

    with pytest.raises(
        ValueError,
        match=(
            "BLOCKED項目はblocks_new_entries=True"
            "である必要があります。"
        ),
    ):
        make_item(
            name="daily_loss",
            status=RiskReportStatus.BLOCKED,
            reason=RiskReportReason.DAILY_LOSS_BLOCKED,
            message="停止しています。",
            blocks_new_entries=False,
        )


def test_clear_item_requires_all_clear_reason() -> None:
    """CLEAR項目にはALL_CLEAR理由を要求する。"""

    with pytest.raises(
        ValueError,
        match=(
            "CLEAR項目のreasonはALL_CLEAR"
            "である必要があります。"
        ),
    ):
        make_item(
            name="daily_loss",
            status=RiskReportStatus.CLEAR,
            reason=RiskReportReason.DAILY_LOSS_WARNING,
            message="正常です。",
            blocks_new_entries=False,
        )


def test_item_metadata_is_preserved() -> None:
    """個別項目のmetadataを保持する。"""

    metadata = {
        "total_loss": 50_000.0,
        "limit": 100_000.0,
    }

    item = make_item(
        name="daily_loss",
        status=RiskReportStatus.WARNING,
        reason=RiskReportReason.DAILY_LOSS_WARNING,
        message="警告です。",
        blocks_new_entries=False,
        metadata=metadata,
    )

    assert item.metadata == metadata


@pytest.mark.parametrize(
    (
        "reason",
        "name",
    ),
    (
        (
            RiskReportReason.POSITION_SIZE_REJECTED,
            "position_sizing",
        ),
        (
            RiskReportReason.DAILY_LOSS_BLOCKED,
            "daily_loss",
        ),
        (
            RiskReportReason.CONSECUTIVE_LOSS_BLOCKED,
            "consecutive_loss",
        ),
        (
            RiskReportReason.KILL_SWITCH_BLOCKED,
            "kill_switch",
        ),
        (
            RiskReportReason.RUNTIME_HEALTH_ERROR,
            "runtime_health",
        ),
        (
            RiskReportReason.HEARTBEAT_STALE,
            "heartbeat",
        ),
        (
            RiskReportReason.BROKER_UNAVAILABLE,
            "broker",
        ),
    ),
)
def test_supported_blocking_reasons_are_aggregated(
    service: RiskReportService,
    reason: RiskReportReason,
    name: str,
) -> None:
    """各停止理由を統合レポートへ集約できる。"""

    report = service.generate(
        make_snapshot(
            items=(
                blocked_item(
                    name=name,
                    reason=reason,
                ),
            ),
        )
    )

    assert report.status is RiskReportStatus.BLOCKED
    assert report.primary_reason is reason
    assert report.blocking_reasons == (reason,)
