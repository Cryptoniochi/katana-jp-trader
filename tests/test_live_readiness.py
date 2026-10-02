"""Live専用Readinessのテスト。"""

import json
from datetime import datetime, timezone

from app.live.execution_mode import (
    ExecutionModeSettings,
    TradingExecutionMode,
)
from app.live.kabu_station_read_only import (
    KabuStationReadOnlySnapshot,
)
from app.live.live_readiness import LiveReadinessChecker


def snapshot(*, connected=True, orders=()):
    return KabuStationReadOnlySnapshot(
        generated_at=datetime.now(timezone.utc),
        state="complete" if connected else "failed",
        connected=connected,
        token_issued=connected,
        cash_wallet={} if connected else None,
        margin_wallet={} if connected else None,
        positions=(),
        orders=tuple(orders),
        errors=() if connected else ("connection failed",),
    )


def write_shadow(path, *, consistent=True, issue_count=0):
    path.write_text(
        json.dumps({
            "consistent": consistent,
            "issue_count": issue_count,
        }),
        encoding="utf-8",
    )


def test_read_only_can_be_ready_while_live_orders_remain_blocked(tmp_path):
    shadow = tmp_path / "shadow.json"
    write_shadow(shadow)

    report = LiveReadinessChecker().check(
        snapshot=snapshot(),
        execution_settings=ExecutionModeSettings(),
        shadow_report_path=shadow,
    )

    assert report.read_only_ready is True
    assert report.shadow_ready is True
    assert report.live_order_ready is False
    assert report.state == "live_read_only_ready"


def test_live_unlock_environment_is_reported_as_unsafe(tmp_path):
    shadow = tmp_path / "shadow.json"
    write_shadow(shadow)

    report = LiveReadinessChecker().check(
        snapshot=snapshot(),
        execution_settings=ExecutionModeSettings(
            mode=TradingExecutionMode.LIVE,
            live_armed=True,
            live_confirmation="KATANA-LIVE-2026-10-03",
        ),
        shadow_report_path=shadow,
    )

    assert report.read_only_ready is False
    lock = next(item for item in report.items if item.key == "live_order_lock")
    assert lock.passed is False


def test_active_broker_order_is_visible_and_fails_its_check(tmp_path):
    shadow = tmp_path / "shadow.json"
    write_shadow(shadow)

    report = LiveReadinessChecker().check(
        snapshot=snapshot(orders=({"State": 3},)),
        execution_settings=ExecutionModeSettings(),
        shadow_report_path=shadow,
    )

    item = next(
        item for item in report.items if item.key == "broker_active_orders"
    )
    assert item.passed is False
    assert "count=1" in item.message
    assert report.live_order_ready is False
