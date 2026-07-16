"""PortfolioRepositoryの統合テスト。"""

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.database import SCHEMA_VERSION, initialize_database
from app.trading.broker_adapter import BrokerPositionSide
from app.trading.portfolio_models import (
    PortfolioPositionSnapshot,
    PortfolioSnapshot,
)
from app.trading.portfolio_repository import (
    DuplicatePortfolioSnapshotError,
    PortfolioRepository,
    PortfolioSnapshotNotFoundError,
)


GENERATED_AT = datetime(
    2026,
    7,
    20,
    1,
    0,
    tzinfo=timezone.utc,
)
CREATED_AT = GENERATED_AT + timedelta(seconds=1)


def create_snapshot(
    *,
    generated_at: datetime = GENERATED_AT,
    with_position: bool = True,
) -> PortfolioSnapshot:
    positions = (
        (
            PortfolioPositionSnapshot(
                position_id="position-7203-long",
                code="7203",
                side=BrokerPositionSide.LONG,
                quantity=100,
                average_cost=2500.0,
                market_price=2600.0,
                realized_profit_loss=5000.0,
            ),
        )
        if with_position
        else ()
    )

    return PortfolioSnapshot(
        currency="JPY",
        cash_balance=750_000.0,
        buying_power=750_000.0,
        broker_market_value=260_000.0 if with_position else 0.0,
        broker_equity=1_010_000.0 if with_position else 750_000.0,
        positions=positions,
        generated_at=generated_at,
    )


def create_repository(
    tmp_path: Path,
) -> tuple[Path, PortfolioRepository]:
    database_path = tmp_path / "katana.db"
    initialize_database(database_path)

    return (
        database_path,
        PortfolioRepository(
            database_path,
            now_provider=lambda: CREATED_AT,
        ),
    )


def test_initialize_database_creates_portfolio_tables(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "katana.db"
    initialize_database(database_path)

    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name IN (
                  'portfolio_snapshots',
                  'portfolio_snapshot_positions'
              )
            ORDER BY name
            """
        ).fetchall()
        version_row = connection.execute(
            """
            SELECT version
            FROM schema_version
            WHERE id = 1
            """
        ).fetchone()

    assert rows == [
        ("portfolio_snapshot_positions",),
        ("portfolio_snapshots",),
    ]
    assert version_row == (SCHEMA_VERSION,)
    assert SCHEMA_VERSION == 10


def test_repository_saves_and_reads_snapshot(
    tmp_path: Path,
) -> None:
    _database_path, repository = create_repository(tmp_path)
    snapshot = create_snapshot()

    saved = repository.save(snapshot)

    assert saved == snapshot
    assert repository.get(GENERATED_AT) == snapshot
    assert repository.count() == 1


def test_repository_saves_empty_snapshot(
    tmp_path: Path,
) -> None:
    _database_path, repository = create_repository(tmp_path)
    snapshot = create_snapshot(with_position=False)

    saved = repository.save(snapshot)

    assert saved.position_count == 0
    assert saved.positions == ()
    assert repository.count() == 1


def test_repository_rejects_duplicate_generated_at(
    tmp_path: Path,
) -> None:
    _database_path, repository = create_repository(tmp_path)
    repository.save(create_snapshot())

    with pytest.raises(
        DuplicatePortfolioSnapshotError,
        match="同じ集計日時",
    ):
        repository.save(create_snapshot())


def test_repository_returns_latest_snapshot(
    tmp_path: Path,
) -> None:
    _database_path, repository = create_repository(tmp_path)
    earlier = create_snapshot()
    later = create_snapshot(
        generated_at=GENERATED_AT + timedelta(minutes=1),
        with_position=False,
    )

    repository.save(earlier)
    repository.save(later)

    assert repository.latest() == later
    assert repository.count() == 2


def test_repository_returns_none_when_empty(
    tmp_path: Path,
) -> None:
    _database_path, repository = create_repository(tmp_path)

    assert repository.latest() is None
    assert repository.list_recent() == []
    assert repository.count() == 0


def test_repository_lists_recent_snapshots(
    tmp_path: Path,
) -> None:
    _database_path, repository = create_repository(tmp_path)
    earlier = create_snapshot()
    later = create_snapshot(
        generated_at=GENERATED_AT + timedelta(minutes=1),
        with_position=False,
    )

    repository.save(earlier)
    repository.save(later)

    assert repository.list_recent() == [later, earlier]
    assert repository.list_recent(limit=1) == [later]


def test_repository_rejects_missing_snapshot(
    tmp_path: Path,
) -> None:
    _database_path, repository = create_repository(tmp_path)

    with pytest.raises(
        PortfolioSnapshotNotFoundError,
        match="存在しません",
    ):
        repository.get(GENERATED_AT)


def test_repository_rejects_invalid_limit(
    tmp_path: Path,
) -> None:
    _database_path, repository = create_repository(tmp_path)

    with pytest.raises(ValueError, match="取得件数"):
        repository.list_recent(limit=0)


def test_repository_normalizes_generated_at_to_utc(
    tmp_path: Path,
) -> None:
    _database_path, repository = create_repository(tmp_path)
    jst = timezone(timedelta(hours=9))
    jst_generated_at = datetime(
        2026,
        7,
        20,
        10,
        0,
        tzinfo=jst,
    )

    saved = repository.save(
        create_snapshot(
            generated_at=jst_generated_at
        )
    )

    assert saved.generated_at == GENERATED_AT
