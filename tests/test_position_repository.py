"""現在ポジションモデルとRepositoryのテスト。"""

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.database import SCHEMA_VERSION, initialize_database
from app.trading.broker_adapter import BrokerPositionSide
from app.trading.position_models import TradingPosition
from app.trading.position_repository import (
    DuplicatePositionError,
    PositionNotFoundError,
    PositionRepository,
)


CREATED_AT = datetime(
    2026,
    7,
    20,
    0,
    30,
    tzinfo=timezone.utc,
)
UPDATED_AT = CREATED_AT + timedelta(minutes=5)


class SequentialClock:
    """指定日時を順番に返す時計。"""

    def __init__(self, values: list[datetime]) -> None:
        self.values = iter(values)

    def now(self) -> datetime:
        return next(self.values)


def create_position(
    *,
    position_id: str = "position-7203-long",
    code: str = "7203",
    side: BrokerPositionSide = BrokerPositionSide.LONG,
    quantity: int = 100,
    average_cost: float = 2500.0,
    realized_profit_loss: float = 0.0,
    opened_at: datetime = CREATED_AT,
) -> TradingPosition:
    """標準的な現在ポジションを作成する。"""

    return TradingPosition(
        position_id=position_id,
        code=code,
        side=side,
        quantity=quantity,
        average_cost=average_cost,
        realized_profit_loss=realized_profit_loss,
        opened_at=opened_at,
    )


def create_repository(
    tmp_path: Path,
    *,
    times: list[datetime] | None = None,
) -> tuple[Path, PositionRepository]:
    """初期化済みDBとRepositoryを作成する。"""

    database_path = tmp_path / "katana.db"
    initialize_database(database_path)

    return (
        database_path,
        PositionRepository(
            database_path,
            now_provider=SequentialClock(
                times or [CREATED_AT]
            ).now,
        ),
    )


def test_initialize_database_creates_positions_table(
    tmp_path: Path,
) -> None:
    """DB初期化でpositionsテーブルを作成する。"""

    database_path = tmp_path / "katana.db"
    initialize_database(database_path)

    with sqlite3.connect(database_path) as connection:
        table_row = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name = 'positions'
            """
        ).fetchone()
        version_row = connection.execute(
            """
            SELECT version
            FROM schema_version
            WHERE id = 1
            """
        ).fetchone()

    assert table_row == ("positions",)
    assert version_row == (SCHEMA_VERSION,)
    assert SCHEMA_VERSION == 9


def test_repository_creates_and_reads_position(
    tmp_path: Path,
) -> None:
    """現在ポジションを保存して読み込む。"""

    _database_path, repository = create_repository(tmp_path)

    position = create_position()
    record = repository.create(position)

    assert record.id > 0
    assert record.position == position
    assert record.created_at == CREATED_AT
    assert record.updated_at == CREATED_AT
    assert record.position.acquisition_value == pytest.approx(
        250_000.0
    )
    assert repository.get(position.position_id) == record
    assert repository.get_by_identity(
        code="7203",
        side=BrokerPositionSide.LONG,
    ) == record


def test_repository_rejects_duplicate_position_id(
    tmp_path: Path,
) -> None:
    """同じポジションIDを拒否する。"""

    _database_path, repository = create_repository(
        tmp_path,
        times=[CREATED_AT, UPDATED_AT],
    )
    repository.create(create_position())

    with pytest.raises(
        DuplicatePositionError,
        match="ポジションID",
    ):
        repository.create(create_position())


def test_repository_rejects_duplicate_code_and_side(
    tmp_path: Path,
) -> None:
    """同じ銘柄・方向の2件目を拒否する。"""

    _database_path, repository = create_repository(
        tmp_path,
        times=[CREATED_AT, UPDATED_AT],
    )
    repository.create(create_position())

    with pytest.raises(DuplicatePositionError):
        repository.create(
            create_position(
                position_id="position-other",
            )
        )


def test_repository_updates_position(
    tmp_path: Path,
) -> None:
    """数量・平均取得価格・実現損益を更新する。"""

    _database_path, repository = create_repository(
        tmp_path,
        times=[CREATED_AT, UPDATED_AT],
    )
    repository.create(create_position())

    updated = repository.update(
        create_position(
            quantity=150,
            average_cost=2520.0,
            realized_profit_loss=500.0,
        )
    )

    assert updated.quantity == 150
    assert updated.position.average_cost == pytest.approx(2520.0)
    assert updated.position.realized_profit_loss == pytest.approx(
        500.0
    )
    assert updated.created_at == CREATED_AT
    assert updated.updated_at == UPDATED_AT


def test_repository_rejects_identity_change_on_update(
    tmp_path: Path,
) -> None:
    """更新時の銘柄または方向変更を拒否する。"""

    _database_path, repository = create_repository(
        tmp_path,
        times=[CREATED_AT],
    )
    repository.create(create_position())

    with pytest.raises(ValueError, match="変更できません"):
        repository.update(
            create_position(code="8306")
        )


def test_repository_lists_and_filters_positions(
    tmp_path: Path,
) -> None:
    """銘柄と方向で現在ポジションを絞り込む。"""

    _database_path, repository = create_repository(tmp_path)
    repository.create(create_position())

    assert len(repository.list_recent(code="7203")) == 1
    assert len(
        repository.list_recent(
            side=BrokerPositionSide.LONG
        )
    ) == 1
    assert repository.count(code="7203") == 1
    assert repository.count(
        side=BrokerPositionSide.LONG
    ) == 1


def test_repository_returns_none_without_identity(
    tmp_path: Path,
) -> None:
    """存在しない銘柄・方向にはNoneを返す。"""

    _database_path, repository = create_repository(tmp_path)

    assert repository.get_by_identity(
        code="7203",
        side=BrokerPositionSide.LONG,
    ) is None
    assert repository.count() == 0


def test_repository_rejects_missing_position(
    tmp_path: Path,
) -> None:
    """存在しないポジションIDを拒否する。"""

    _database_path, repository = create_repository(tmp_path)

    with pytest.raises(
        PositionNotFoundError,
        match="存在しません",
    ):
        repository.get("missing-position")


def test_repository_rejects_invalid_limit(
    tmp_path: Path,
) -> None:
    """0以下の取得件数を拒否する。"""

    _database_path, repository = create_repository(tmp_path)

    with pytest.raises(ValueError, match="取得件数"):
        repository.list_recent(limit=0)


def test_repository_normalizes_opened_at_to_utc(
    tmp_path: Path,
) -> None:
    """ポジション開始日時をUTCへ正規化する。"""

    _database_path, repository = create_repository(tmp_path)
    jst = timezone(timedelta(hours=9))

    record = repository.create(
        create_position(
            opened_at=datetime(
                2026,
                7,
                20,
                9,
                30,
                tzinfo=jst,
            )
        )
    )

    assert record.position.opened_at == CREATED_AT


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        ({"position_id": " "}, "ポジションID"),
        ({"code": "ABC"}, "数字"),
        ({"quantity": 0}, "保有数量"),
        ({"average_cost": 0.0}, "平均取得価格"),
    ],
)
def test_position_rejects_invalid_values(
    arguments: dict[str, object],
    message: str,
) -> None:
    """不正な現在ポジションを拒否する。"""

    base_arguments: dict[str, object] = {
        "position_id": "position-7203-long",
        "code": "7203",
        "side": BrokerPositionSide.LONG,
        "quantity": 100,
        "average_cost": 2500.0,
        "realized_profit_loss": 0.0,
        "opened_at": CREATED_AT,
    }
    base_arguments.update(arguments)

    with pytest.raises((TypeError, ValueError), match=message):
        TradingPosition(**base_arguments)


def test_position_rejects_naive_opened_at() -> None:
    """タイムゾーンなし開始日時を拒否する。"""

    with pytest.raises(ValueError, match="タイムゾーン"):
        create_position(
            opened_at=datetime(
                2026,
                7,
                20,
                9,
                30,
            )
        )
