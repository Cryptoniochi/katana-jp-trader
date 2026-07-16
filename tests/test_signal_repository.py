"""売買シグナルモデルとRepositoryのテスト。"""

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.database import (
    SCHEMA_VERSION,
    initialize_database,
)
from app.trading.signal_models import (
    SignalAction,
    SignalStatus,
    TradeSignal,
)
from app.trading.signal_repository import (
    DuplicateSignalError,
    SignalNotFoundError,
    SignalRepository,
    SignalStateTransitionError,
)


GENERATED_AT = datetime(
    2026,
    7,
    16,
    9,
    20,
    tzinfo=timezone.utc,
)

CREATED_AT = datetime(
    2026,
    7,
    16,
    9,
    21,
    tzinfo=timezone.utc,
)

PROCESSED_AT = datetime(
    2026,
    7,
    16,
    9,
    22,
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
            times,
        )

    def now(self) -> datetime:
        """次の日時を返す。"""

        return next(
            self.times,
        )


def create_signal(
    *,
    signal_id: str = "signal-001",
    code: str = "7203",
    strategy_name: str = "orb",
    action: SignalAction = SignalAction.BUY,
    generated_at: datetime = GENERATED_AT,
    signal_price: float = 2500.0,
    quantity: int = 100,
    reason: str = "opening_range_breakout",
    confidence: float | None = 0.8,
) -> TradeSignal:
    """標準的なテスト用売買シグナルを作成する。"""

    return TradeSignal(
        signal_id=signal_id,
        code=code,
        strategy_name=strategy_name,
        action=action,
        generated_at=generated_at,
        signal_price=signal_price,
        quantity=quantity,
        reason=reason,
        confidence=confidence,
        metadata={
            "opening_range_high": 2480.0,
            "breakout_volume": 150_000,
            "trade_candidate": True,
        },
    )


def create_repository(
    tmp_path: Path,
    *,
    times: list[datetime] | None = None,
) -> tuple[
    Path,
    SignalRepository,
]:
    """初期化済みDBとSignalRepositoryを作成する。"""

    database_path = (
        tmp_path / "katana.db"
    )

    initialize_database(
        database_path,
    )

    clock = SequentialClock(
        times or [CREATED_AT],
    )

    repository = SignalRepository(
        database_path,
        now_provider=clock.now,
    )

    return database_path, repository


def test_initialize_database_creates_trade_signals_table(
    tmp_path: Path,
) -> None:
    """DB初期化でtrade_signalsテーブルを作成する。"""

    database_path = (
        tmp_path / "katana.db"
    )

    initialize_database(
        database_path,
    )

    with sqlite3.connect(
        database_path,
    ) as connection:
        table_row = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name = 'trade_signals'
            """
        ).fetchone()

        version_row = connection.execute(
            """
            SELECT version
            FROM schema_version
            WHERE id = 1
            """
        ).fetchone()

    assert table_row == (
        "trade_signals",
    )
    assert version_row == (
        SCHEMA_VERSION,
    )
    assert SCHEMA_VERSION == 10


def test_initialize_database_remains_idempotent(
    tmp_path: Path,
) -> None:
    """DB初期化を複数回実行してもシグナル表を維持する。"""

    database_path = (
        tmp_path / "katana.db"
    )

    initialize_database(
        database_path,
    )
    initialize_database(
        database_path,
    )

    with sqlite3.connect(
        database_path,
    ) as connection:
        count_row = connection.execute(
            """
            SELECT COUNT(*)
            FROM sqlite_master
            WHERE type = 'table'
              AND name = 'trade_signals'
            """
        ).fetchone()

    assert count_row == (
        1,
    )


def test_repository_saves_pending_signal(
    tmp_path: Path,
) -> None:
    """シグナルを未処理状態で保存する。"""

    _database_path, repository = create_repository(
        tmp_path,
    )

    signal = create_signal()

    record = repository.save(
        signal,
    )

    assert record.id > 0
    assert record.signal == signal
    assert record.status is SignalStatus.PENDING
    assert record.is_pending is True
    assert record.is_processed is False
    assert record.is_cancelled is False
    assert record.processed_at is None
    assert record.process_note is None
    assert record.created_at == CREATED_AT
    assert record.updated_at == CREATED_AT

    loaded = repository.get(
        signal.signal_id,
    )

    assert loaded == record


def test_repository_preserves_metadata(
    tmp_path: Path,
) -> None:
    """JSONメタデータを保存して復元する。"""

    _database_path, repository = create_repository(
        tmp_path,
    )

    signal = create_signal()

    repository.save(
        signal,
    )

    loaded = repository.get(
        signal.signal_id,
    )

    assert loaded.signal.metadata == {
        "breakout_volume": 150_000,
        "opening_range_high": 2480.0,
        "trade_candidate": True,
    }


def test_repository_saves_all_actions(
    tmp_path: Path,
) -> None:
    """BUY・SELL・EXITをそれぞれ保存できる。"""

    _database_path, repository = create_repository(
        tmp_path,
        times=[
            CREATED_AT,
            CREATED_AT + timedelta(seconds=1),
            CREATED_AT + timedelta(seconds=2),
        ],
    )

    repository.save(
        create_signal(
            signal_id="buy-001",
            action=SignalAction.BUY,
            generated_at=GENERATED_AT,
        )
    )

    repository.save(
        create_signal(
            signal_id="sell-001",
            action=SignalAction.SELL,
            generated_at=(
                GENERATED_AT
                + timedelta(minutes=1)
            ),
        )
    )

    repository.save(
        create_signal(
            signal_id="exit-001",
            action=SignalAction.EXIT,
            generated_at=(
                GENERATED_AT
                + timedelta(minutes=2)
            ),
        )
    )

    assert repository.count(
        action=SignalAction.BUY,
    ) == 1

    assert repository.count(
        action=SignalAction.SELL,
    ) == 1

    assert repository.count(
        action=SignalAction.EXIT,
    ) == 1


def test_repository_rejects_duplicate_signal_id(
    tmp_path: Path,
) -> None:
    """同一シグナルIDの重複保存を拒否する。"""

    _database_path, repository = create_repository(
        tmp_path,
        times=[
            CREATED_AT,
            CREATED_AT + timedelta(seconds=1),
        ],
    )

    repository.save(
        create_signal(),
    )

    with pytest.raises(
        DuplicateSignalError,
        match="既に存在",
    ):
        repository.save(
            create_signal(
                generated_at=(
                    GENERATED_AT
                    + timedelta(minutes=1)
                ),
            )
        )


def test_repository_rejects_duplicate_signal_identity(
    tmp_path: Path,
) -> None:
    """同一銘柄・戦略・売買指示・生成日時を拒否する。"""

    _database_path, repository = create_repository(
        tmp_path,
        times=[
            CREATED_AT,
            CREATED_AT + timedelta(seconds=1),
        ],
    )

    repository.save(
        create_signal(
            signal_id="signal-001",
        )
    )

    with pytest.raises(
        DuplicateSignalError,
        match="既に存在",
    ):
        repository.save(
            create_signal(
                signal_id="signal-002",
            )
        )


def test_repository_lists_recent_signals(
    tmp_path: Path,
) -> None:
    """シグナルを生成日時の新しい順に返す。"""

    _database_path, repository = create_repository(
        tmp_path,
        times=[
            CREATED_AT,
            CREATED_AT + timedelta(seconds=1),
            CREATED_AT + timedelta(seconds=2),
        ],
    )

    repository.save(
        create_signal(
            signal_id="signal-001",
            generated_at=GENERATED_AT,
        )
    )

    repository.save(
        create_signal(
            signal_id="signal-002",
            generated_at=(
                GENERATED_AT
                + timedelta(minutes=1)
            ),
        )
    )

    repository.save(
        create_signal(
            signal_id="signal-003",
            generated_at=(
                GENERATED_AT
                + timedelta(minutes=2)
            ),
        )
    )

    records = repository.list_recent(
        limit=2,
    )

    assert [
        record.signal_id
        for record in records
    ] == [
        "signal-003",
        "signal-002",
    ]


def test_repository_filters_signals(
    tmp_path: Path,
) -> None:
    """銘柄・戦略・状態・売買指示で絞り込む。"""

    _database_path, repository = create_repository(
        tmp_path,
        times=[
            CREATED_AT,
            CREATED_AT + timedelta(seconds=1),
            CREATED_AT + timedelta(seconds=2),
        ],
    )

    repository.save(
        create_signal(
            signal_id="signal-001",
            code="7203",
            strategy_name="orb",
            action=SignalAction.BUY,
            generated_at=GENERATED_AT,
        )
    )

    repository.save(
        create_signal(
            signal_id="signal-002",
            code="8306",
            strategy_name="orb",
            action=SignalAction.BUY,
            generated_at=(
                GENERATED_AT
                + timedelta(minutes=1)
            ),
        )
    )

    repository.save(
        create_signal(
            signal_id="signal-003",
            code="7203",
            strategy_name="momentum",
            action=SignalAction.SELL,
            generated_at=(
                GENERATED_AT
                + timedelta(minutes=2)
            ),
        )
    )

    records = repository.list_recent(
        code="7203",
        strategy_name="orb",
        status=SignalStatus.PENDING,
        action=SignalAction.BUY,
    )

    assert [
        record.signal_id
        for record in records
    ] == [
        "signal-001",
    ]


def test_repository_returns_latest_signal(
    tmp_path: Path,
) -> None:
    """条件に一致する最新シグナルを返す。"""

    _database_path, repository = create_repository(
        tmp_path,
        times=[
            CREATED_AT,
            CREATED_AT + timedelta(seconds=1),
        ],
    )

    repository.save(
        create_signal(
            signal_id="signal-001",
            generated_at=GENERATED_AT,
        )
    )

    repository.save(
        create_signal(
            signal_id="signal-002",
            generated_at=(
                GENERATED_AT
                + timedelta(minutes=1)
            ),
        )
    )

    latest = repository.latest(
        code="7203",
        strategy_name="orb",
    )

    assert latest is not None
    assert latest.signal_id == "signal-002"


def test_repository_returns_none_without_signal(
    tmp_path: Path,
) -> None:
    """保存済みシグナルがなければNoneを返す。"""

    _database_path, repository = create_repository(
        tmp_path,
    )

    assert repository.latest() is None
    assert repository.list_pending() == []
    assert repository.count() == 0


def test_repository_marks_signal_processed(
    tmp_path: Path,
) -> None:
    """未処理シグナルを処理済みに更新する。"""

    _database_path, repository = create_repository(
        tmp_path,
        times=[
            CREATED_AT,
            PROCESSED_AT,
        ],
    )

    repository.save(
        create_signal(),
    )

    record = repository.mark_processed(
        "signal-001",
        process_note="order request created",
    )

    assert record.status is SignalStatus.PROCESSED
    assert record.is_processed is True
    assert record.is_pending is False
    assert record.processed_at == PROCESSED_AT
    assert record.process_note == (
        "order request created"
    )
    assert record.updated_at == PROCESSED_AT

    assert repository.count(
        status=SignalStatus.PROCESSED,
    ) == 1
    assert repository.list_pending() == []


def test_repository_cancels_signal(
    tmp_path: Path,
) -> None:
    """未処理シグナルを取消済みに更新する。"""

    _database_path, repository = create_repository(
        tmp_path,
        times=[
            CREATED_AT,
            PROCESSED_AT,
        ],
    )

    repository.save(
        create_signal(),
    )

    record = repository.cancel(
        "signal-001",
        process_note="risk filter rejected",
    )

    assert record.status is SignalStatus.CANCELLED
    assert record.is_cancelled is True
    assert record.processed_at == PROCESSED_AT
    assert record.process_note == (
        "risk filter rejected"
    )


def test_repository_rejects_second_state_transition(
    tmp_path: Path,
) -> None:
    """処理済みシグナルの再処理を拒否する。"""

    _database_path, repository = create_repository(
        tmp_path,
        times=[
            CREATED_AT,
            PROCESSED_AT,
        ],
    )

    repository.save(
        create_signal(),
    )

    repository.mark_processed(
        "signal-001",
    )

    with pytest.raises(
        SignalStateTransitionError,
        match="状態変更",
    ):
        repository.cancel(
            "signal-001",
        )


def test_repository_rejects_missing_signal(
    tmp_path: Path,
) -> None:
    """存在しないシグナルIDを拒否する。"""

    _database_path, repository = create_repository(
        tmp_path,
    )

    with pytest.raises(
        SignalNotFoundError,
        match="存在しません",
    ):
        repository.get(
            "missing-signal",
        )


def test_repository_rejects_invalid_limit(
    tmp_path: Path,
) -> None:
    """0以下の取得件数を拒否する。"""

    _database_path, repository = create_repository(
        tmp_path,
    )

    with pytest.raises(
        ValueError,
        match="取得件数",
    ):
        repository.list_recent(
            limit=0,
        )


def test_repository_rejects_non_json_metadata(
    tmp_path: Path,
) -> None:
    """JSON化できないメタデータの保存を拒否する。"""

    _database_path, repository = create_repository(
        tmp_path,
    )

    signal = TradeSignal(
        signal_id="signal-001",
        code="7203",
        strategy_name="orb",
        action=SignalAction.BUY,
        generated_at=GENERATED_AT,
        signal_price=2500.0,
        quantity=100,
        reason="opening_range_breakout",
        metadata={
            "invalid": object(),
        },
    )

    with pytest.raises(
        ValueError,
        match="JSON",
    ):
        repository.save(
            signal,
        )


@pytest.mark.parametrize(
    (
        "arguments",
        "message",
    ),
    [
        (
            {
                "signal_id": " ",
            },
            "シグナルID",
        ),
        (
            {
                "code": "ABC",
            },
            "数字",
        ),
        (
            {
                "code": "123",
            },
            "4桁",
        ),
        (
            {
                "strategy_name": " ",
            },
            "戦略名",
        ),
        (
            {
                "signal_price": 0,
            },
            "シグナル価格",
        ),
        (
            {
                "quantity": 0,
            },
            "数量",
        ),
        (
            {
                "reason": " ",
            },
            "シグナル理由",
        ),
        (
            {
                "confidence": -0.1,
            },
            "信頼度",
        ),
        (
            {
                "confidence": 1.1,
            },
            "信頼度",
        ),
    ],
)
def test_trade_signal_rejects_invalid_values(
    arguments: dict[str, object],
    message: str,
) -> None:
    """不正な売買シグナルを拒否する。"""

    base_arguments: dict[str, object] = {
        "signal_id": "signal-001",
        "code": "7203",
        "strategy_name": "orb",
        "action": SignalAction.BUY,
        "generated_at": GENERATED_AT,
        "signal_price": 2500.0,
        "quantity": 100,
        "reason": "opening_range_breakout",
    }

    base_arguments.update(
        arguments,
    )

    with pytest.raises(
        (
            TypeError,
            ValueError,
        ),
        match=message,
    ):
        TradeSignal(
            **base_arguments,
        )


def test_trade_signal_rejects_naive_generated_time() -> None:
    """タイムゾーンなしの生成日時を拒否する。"""

    with pytest.raises(
        ValueError,
        match="タイムゾーン",
    ):
        create_signal(
            generated_at=datetime(
                2026,
                7,
                16,
                9,
                20,
            ),
        )


def test_repository_rejects_naive_current_time(
    tmp_path: Path,
) -> None:
    """Repositoryのタイムゾーンなし現在日時を拒否する。"""

    database_path = (
        tmp_path / "katana.db"
    )

    initialize_database(
        database_path,
    )

    repository = SignalRepository(
        database_path,
        now_provider=lambda: datetime(
            2026,
            7,
            16,
            9,
            21,
        ),
    )

    with pytest.raises(
        ValueError,
        match="タイムゾーン",
    ):
        repository.save(
            create_signal(),
        )