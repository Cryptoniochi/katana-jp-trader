"""LiveOperationLogServiceのテスト。"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from app.live.live_operation_log_models import (
    LiveLogEventType,
    LiveLogLevel,
    LiveOperationLogEntry,
)
from app.live.live_operation_log_service import (
    LiveOperationLogError,
    LiveOperationLogService,
)


TRADING_DATE = date(2026, 7, 17)


def entry(
    *,
    second: int,
    event_type: LiveLogEventType,
    level: LiveLogLevel = LiveLogLevel.INFO,
    code: str | None = None,
    cycle_number: int | None = 1,
    metadata: dict[str, object] | None = None,
) -> LiveOperationLogEntry:
    """テスト用ログを作成する。"""

    return LiveOperationLogEntry(
        occurred_at=datetime(
            2026,
            7,
            17,
            0,
            0,
            second,
            tzinfo=timezone.utc,
        ),
        level=level,
        event_type=event_type,
        message=f"{event_type.value} message",
        cycle_number=cycle_number,
        code=code,
        metadata=metadata or {},
    )


def test_append_and_read_date(
    tmp_path: Path,
) -> None:
    """JSONLへ追記し、発生順に読み戻す。"""

    service = LiveOperationLogService(
        log_directory=tmp_path
    )

    service.append(
        entry(
            second=2,
            event_type=LiveLogEventType.CYCLE_COMPLETED,
        )
    )
    service.append(
        entry(
            second=1,
            event_type=LiveLogEventType.CYCLE_STARTED,
        )
    )

    entries = service.read_date(TRADING_DATE)

    assert len(entries) == 2
    assert entries[0].event_type is (
        LiveLogEventType.CYCLE_STARTED
    )
    assert entries[1].event_type is (
        LiveLogEventType.CYCLE_COMPLETED
    )


def test_append_all_returns_unique_paths(
    tmp_path: Path,
) -> None:
    """同じ日付の複数ログではパスを重複させない。"""

    service = LiveOperationLogService(
        log_directory=tmp_path
    )

    paths = service.append_all(
        (
            entry(
                second=1,
                event_type=LiveLogEventType.SIGNAL,
            ),
            entry(
                second=2,
                event_type=LiveLogEventType.ORDER,
            ),
        )
    )

    assert len(paths) == 1
    assert paths[0].name == "2026-07-17.jsonl"


def test_create_daily_summary(
    tmp_path: Path,
) -> None:
    """イベント・リスク・エラー件数を集計する。"""

    service = LiveOperationLogService(
        log_directory=tmp_path
    )
    service.append_all(
        (
            entry(
                second=1,
                event_type=LiveLogEventType.CYCLE_STARTED,
            ),
            entry(
                second=2,
                event_type=LiveLogEventType.MARKET_POLL,
            ),
            entry(
                second=3,
                event_type=LiveLogEventType.SIGNAL,
                code="7203",
            ),
            entry(
                second=4,
                event_type=LiveLogEventType.RISK,
                code="7203",
                level=LiveLogLevel.WARNING,
                metadata={"decision": "rejected"},
            ),
            entry(
                second=5,
                event_type=LiveLogEventType.RISK,
                code="6758",
                level=LiveLogLevel.CRITICAL,
                metadata={"decision": "halted"},
            ),
            entry(
                second=6,
                event_type=LiveLogEventType.ORDER,
                code="7203",
            ),
            entry(
                second=7,
                event_type=LiveLogEventType.EXECUTION,
                code="7203",
            ),
            entry(
                second=8,
                event_type=LiveLogEventType.ERROR,
                level=LiveLogLevel.ERROR,
            ),
            entry(
                second=9,
                event_type=LiveLogEventType.CYCLE_COMPLETED,
            ),
        )
    )

    summary = service.create_daily_summary(
        TRADING_DATE
    )

    assert summary.log_count == 9
    assert summary.cycle_started_count == 1
    assert summary.cycle_completed_count == 1
    assert summary.market_poll_count == 1
    assert summary.signal_count == 1
    assert summary.risk_rejected_count == 1
    assert summary.risk_halted_count == 1
    assert summary.order_count == 1
    assert summary.execution_count == 1
    assert summary.error_count == 2
    assert summary.critical_count == 1
    assert summary.codes == ("6758", "7203")


def test_write_daily_summary(
    tmp_path: Path,
) -> None:
    """日次サマリーJSONを保存する。"""

    service = LiveOperationLogService(
        log_directory=tmp_path
    )
    service.append(
        entry(
            second=1,
            event_type=LiveLogEventType.SIGNAL,
            code="7203",
        )
    )

    path = service.write_daily_summary(
        TRADING_DATE
    )
    payload = json.loads(
        path.read_text(encoding="utf-8")
    )

    assert path.name == "2026-07-17_summary.json"
    assert payload["trading_date"] == "2026-07-17"
    assert payload["signal_count"] == 1
    assert payload["codes"] == ["7203"]


def test_read_missing_date_returns_empty(
    tmp_path: Path,
) -> None:
    """ログがない日付では空一覧を返す。"""

    service = LiveOperationLogService(
        log_directory=tmp_path
    )

    assert service.read_date(TRADING_DATE) == ()


def test_read_invalid_json_raises(
    tmp_path: Path,
) -> None:
    """壊れたJSONLを明示的な例外にする。"""

    service = LiveOperationLogService(
        log_directory=tmp_path
    )
    path = service.path_for_date(TRADING_DATE)
    path.write_text(
        "{invalid json}\n",
        encoding="utf-8",
    )

    with pytest.raises(
        LiveOperationLogError,
        match="内容が不正",
    ):
        service.read_date(TRADING_DATE)


def test_log_entry_validates_fields() -> None:
    """ログモデルの不正値を拒否する。"""

    with pytest.raises(ValueError):
        LiveOperationLogEntry(
            occurred_at=datetime(2026, 7, 17),
            level=LiveLogLevel.INFO,
            event_type=LiveLogEventType.ERROR,
            message="error",
        )

    with pytest.raises(ValueError):
        LiveOperationLogEntry(
            occurred_at=datetime.now(timezone.utc),
            level=LiveLogLevel.INFO,
            event_type=LiveLogEventType.ERROR,
            message=" ",
        )

    with pytest.raises(ValueError):
        entry(
            second=1,
            event_type=LiveLogEventType.SIGNAL,
            code="ABC",
        )
