"""売買シグナル重複抑止サービスのテスト。"""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.database import initialize_database
from app.trading.signal_deduplication_service import (
    SignalDeduplicationDecision,
    SignalDeduplicationService,
)
from app.trading.signal_models import (
    SignalAction,
    SignalStatus,
    TradeSignal,
)
from app.trading.signal_repository import (
    SignalRepository,
)


GENERATED_AT = datetime(
    2026,
    7,
    16,
    0,
    20,
    tzinfo=timezone.utc,
)

CREATED_AT = datetime(
    2026,
    7,
    16,
    0,
    21,
    tzinfo=timezone.utc,
)

SECOND_CREATED_AT = datetime(
    2026,
    7,
    16,
    0,
    22,
    tzinfo=timezone.utc,
)

PROCESSED_AT = datetime(
    2026,
    7,
    16,
    0,
    23,
    tzinfo=timezone.utc,
)


class SequentialClock:
    """指定日時を順番に返すテスト用時計。"""

    def __init__(
        self,
        times: list[datetime],
    ) -> None:
        """返却日時を設定する。"""

        self.times = iter(
            times
        )

    def now(self) -> datetime:
        """次の日時を返す。"""

        return next(
            self.times
        )


def create_signal(
    *,
    signal_id: str = "signal-001",
    code: str = "7203",
    strategy_name: str = "orb",
    action: SignalAction = SignalAction.BUY,
    generated_at: datetime = GENERATED_AT,
) -> TradeSignal:
    """重複判定用の標準シグナルを作成する。"""

    return TradeSignal(
        signal_id=signal_id,
        code=code,
        strategy_name=strategy_name,
        action=action,
        generated_at=generated_at,
        signal_price=2500.0,
        quantity=100,
        reason="opening_range_breakout",
        confidence=0.8,
        metadata={
            "trading_date": (
                generated_at
                .astimezone(
                    timezone(
                        timedelta(
                            hours=9
                        )
                    )
                )
                .date()
                .isoformat()
            ),
        },
    )


def create_service(
    tmp_path: Path,
    *,
    times: list[datetime] | None = None,
) -> tuple[
    SignalRepository,
    SignalDeduplicationService,
]:
    """実SQLiteを使用する重複抑止サービスを作成する。"""

    database_path = (
        tmp_path / "katana.db"
    )

    initialize_database(
        database_path
    )

    repository = SignalRepository(
        database_path,
        now_provider=SequentialClock(
            times or [
                CREATED_AT,
                SECOND_CREATED_AT,
                PROCESSED_AT,
            ]
        ).now,
    )

    service = SignalDeduplicationService(
        repository
    )

    return repository, service


def test_service_accepts_first_signal(
    tmp_path: Path,
) -> None:
    """同種シグナルがなければ新規保存する。"""

    repository, service = create_service(
        tmp_path
    )

    signal = create_signal()

    result = service.save_if_unique(
        signal
    )

    assert result.decision is (
        SignalDeduplicationDecision.ACCEPTED
    )
    assert result.is_accepted is True
    assert result.is_duplicate is False
    assert result.is_failed is False
    assert result.signal == signal
    assert result.saved_record is not None
    assert result.duplicate_record is None
    assert result.message is None
    assert result.trading_date.isoformat() == (
        "2026-07-16"
    )

    assert repository.count() == 1
    assert repository.count(
        status=SignalStatus.PENDING
    ) == 1


def test_service_rejects_pending_duplicate_on_same_day(
    tmp_path: Path,
) -> None:
    """同一営業日のPENDINGシグナルを重複として拒否する。"""

    repository, service = create_service(
        tmp_path
    )

    first_result = service.save_if_unique(
        create_signal(
            signal_id="signal-001",
        )
    )

    second_result = service.save_if_unique(
        create_signal(
            signal_id="signal-002",
            generated_at=(
                GENERATED_AT
                + timedelta(minutes=5)
            ),
        )
    )

    assert first_result.is_accepted is True

    assert second_result.decision is (
        SignalDeduplicationDecision.DUPLICATE
    )
    assert second_result.is_duplicate is True
    assert second_result.saved_record is None
    assert second_result.duplicate_record is not None
    assert (
        second_result
        .duplicate_record
        .signal_id
        == "signal-001"
    )
    assert "既に存在" in (
        second_result.message or ""
    )

    assert repository.count() == 1


def test_service_rejects_processed_duplicate_on_same_day(
    tmp_path: Path,
) -> None:
    """同一営業日のPROCESSEDシグナルも重複として拒否する。"""

    repository, service = create_service(
        tmp_path,
        times=[
            CREATED_AT,
            PROCESSED_AT,
        ],
    )

    accepted = service.save_if_unique(
        create_signal(
            signal_id="signal-001",
        )
    )

    assert accepted.saved_record is not None

    repository.mark_processed(
        accepted.saved_record.signal_id,
        process_note="order created",
    )

    duplicate = service.save_if_unique(
        create_signal(
            signal_id="signal-002",
            generated_at=(
                GENERATED_AT
                + timedelta(minutes=10)
            ),
        )
    )

    assert duplicate.is_duplicate is True
    assert duplicate.duplicate_record is not None
    assert duplicate.duplicate_record.status is (
        SignalStatus.PROCESSED
    )
    assert repository.count() == 1


def test_service_allows_replacement_after_cancel(
    tmp_path: Path,
) -> None:
    """既存シグナルがCANCELLEDなら同日の再生成を許可する。"""

    repository, service = create_service(
        tmp_path,
        times=[
            CREATED_AT,
            PROCESSED_AT,
            SECOND_CREATED_AT,
        ],
    )

    accepted = service.save_if_unique(
        create_signal(
            signal_id="signal-001",
        )
    )

    assert accepted.saved_record is not None

    repository.cancel(
        accepted.saved_record.signal_id,
        process_note="risk filter rejected",
    )

    replacement = service.save_if_unique(
        create_signal(
            signal_id="signal-002",
            generated_at=(
                GENERATED_AT
                + timedelta(minutes=10)
            ),
        )
    )

    assert replacement.is_accepted is True
    assert replacement.saved_record is not None
    assert replacement.saved_record.signal_id == (
        "signal-002"
    )

    assert repository.count() == 2
    assert repository.count(
        status=SignalStatus.CANCELLED
    ) == 1
    assert repository.count(
        status=SignalStatus.PENDING
    ) == 1


def test_service_allows_same_signal_type_on_next_day(
    tmp_path: Path,
) -> None:
    """営業日が変われば同じ銘柄・戦略・方向を許可する。"""

    repository, service = create_service(
        tmp_path,
        times=[
            CREATED_AT,
            SECOND_CREATED_AT,
        ],
    )

    first = service.save_if_unique(
        create_signal(
            signal_id="signal-001",
        )
    )

    next_day = service.save_if_unique(
        create_signal(
            signal_id="signal-002",
            generated_at=(
                GENERATED_AT
                + timedelta(days=1)
            ),
        )
    )

    assert first.is_accepted is True
    assert next_day.is_accepted is True
    assert repository.count() == 2


def test_service_allows_different_code_on_same_day(
    tmp_path: Path,
) -> None:
    """銘柄が異なれば同一営業日でも保存する。"""

    repository, service = create_service(
        tmp_path,
        times=[
            CREATED_AT,
            SECOND_CREATED_AT,
        ],
    )

    first = service.save_if_unique(
        create_signal(
            signal_id="signal-001",
            code="7203",
        )
    )

    second = service.save_if_unique(
        create_signal(
            signal_id="signal-002",
            code="8306",
        )
    )

    assert first.is_accepted is True
    assert second.is_accepted is True
    assert repository.count() == 2


def test_service_allows_different_strategy_on_same_day(
    tmp_path: Path,
) -> None:
    """戦略が異なれば同一銘柄・営業日でも保存する。"""

    repository, service = create_service(
        tmp_path,
        times=[
            CREATED_AT,
            SECOND_CREATED_AT,
        ],
    )

    first = service.save_if_unique(
        create_signal(
            signal_id="signal-001",
            strategy_name="orb",
        )
    )

    second = service.save_if_unique(
        create_signal(
            signal_id="signal-002",
            strategy_name="momentum",
        )
    )

    assert first.is_accepted is True
    assert second.is_accepted is True
    assert repository.count() == 2


def test_service_allows_different_action_on_same_day(
    tmp_path: Path,
) -> None:
    """売買方向が異なれば同一銘柄・営業日でも保存する。"""

    repository, service = create_service(
        tmp_path,
        times=[
            CREATED_AT,
            SECOND_CREATED_AT,
        ],
    )

    buy_result = service.save_if_unique(
        create_signal(
            signal_id="signal-001",
            action=SignalAction.BUY,
        )
    )

    exit_result = service.save_if_unique(
        create_signal(
            signal_id="signal-002",
            action=SignalAction.EXIT,
        )
    )

    assert buy_result.is_accepted is True
    assert exit_result.is_accepted is True
    assert repository.count() == 2


def test_service_uses_japan_date_across_utc_boundary(
    tmp_path: Path,
) -> None:
    """UTC日付が異なっても日本時間の同日なら重複と判定する。"""

    repository, service = create_service(
        tmp_path
    )

    first_time = datetime(
        2026,
        7,
        15,
        23,
        30,
        tzinfo=timezone.utc,
    )

    second_time = datetime(
        2026,
        7,
        16,
        1,
        0,
        tzinfo=timezone.utc,
    )

    first = service.save_if_unique(
        create_signal(
            signal_id="signal-001",
            generated_at=first_time,
        )
    )

    second = service.save_if_unique(
        create_signal(
            signal_id="signal-002",
            generated_at=second_time,
        )
    )

    assert first.trading_date.isoformat() == (
        "2026-07-16"
    )
    assert second.trading_date.isoformat() == (
        "2026-07-16"
    )

    assert first.is_accepted is True
    assert second.is_duplicate is True
    assert repository.count() == 1


def test_service_save_many_sorts_and_suppresses_duplicates(
    tmp_path: Path,
) -> None:
    """複数シグナルを時系列処理し最初の1件だけ採用する。"""

    repository, service = create_service(
        tmp_path
    )

    later_signal = create_signal(
        signal_id="signal-later",
        generated_at=(
            GENERATED_AT
            + timedelta(minutes=10)
        ),
    )

    earlier_signal = create_signal(
        signal_id="signal-earlier",
        generated_at=GENERATED_AT,
    )

    result = service.save_many(
        [
            later_signal,
            earlier_signal,
        ]
    )

    assert result.input_count == 2
    assert result.accepted_count == 1
    assert result.duplicate_count == 1
    assert result.failed_count == 0
    assert result.is_successful is True

    assert result.results[0].signal.signal_id == (
        "signal-earlier"
    )
    assert result.results[0].is_accepted is True

    assert result.results[1].signal.signal_id == (
        "signal-later"
    )
    assert result.results[1].is_duplicate is True

    assert len(
        result.saved_records
    ) == 1
    assert (
        result.saved_records[0].signal_id
        == "signal-earlier"
    )
    assert repository.count() == 1


class FailingRepository:
    """常に失敗するテスト用Repository。"""

    def list_recent(
        self,
        *,
        limit: int = 100,
        code: str | None = None,
        strategy_name: str | None = None,
        status: SignalStatus | None = None,
        action: object | None = None,
    ):
        """空の検索結果を返す。"""

        del limit
        del code
        del strategy_name
        del status
        del action

        return []

    def save(
        self,
        signal: TradeSignal,
    ):
        """保存失敗を発生させる。"""

        raise RuntimeError(
            f"save failed: {signal.signal_id}"
        )


def test_service_records_save_failure() -> None:
    """continue_on_error有効時は保存失敗を結果へ記録する。"""

    service = SignalDeduplicationService(
        FailingRepository()
    )

    signal = create_signal()

    result = service.save_if_unique(
        signal,
        continue_on_error=True,
    )

    assert result.decision is (
        SignalDeduplicationDecision.FAILED
    )
    assert result.is_failed is True
    assert result.saved_record is None
    assert result.duplicate_record is None
    assert "save failed" in (
        result.message or ""
    )


def test_service_raises_save_failure_when_continuation_disabled() -> None:
    """continue_on_error無効時は保存失敗を再送出する。"""

    service = SignalDeduplicationService(
        FailingRepository()
    )

    with pytest.raises(
        RuntimeError,
        match="save failed",
    ):
        service.save_if_unique(
            create_signal(),
            continue_on_error=False,
        )


def test_service_rejects_invalid_search_limit() -> None:
    """0以下の重複検索件数を拒否する。"""

    with pytest.raises(
        ValueError,
        match="重複検索件数",
    ):
        SignalDeduplicationService(
            FailingRepository(),
            search_limit=0,
        )