"""HighBreakoutCandidateRepositoryのテスト。"""

import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from app.database import (
    SCHEMA_VERSION,
    initialize_database,
)
from app.strategy.high_breakout_candidate_repository import (
    HighBreakoutCandidateNotFoundError,
    HighBreakoutCandidateRepository,
)
from app.strategy.high_breakout_models import (
    HighBreakoutCandidate,
    HighBreakoutType,
)


NOW = datetime(
    2026,
    8,
    3,
    8,
    0,
    tzinfo=timezone.utc,
)
TRADING_DATE = date(2026, 8, 3)


def candidate(
    *,
    code: str = "7203",
    score: float = 80.0,
    volume_ratio: float = 2.0,
) -> HighBreakoutCandidate:
    return HighBreakoutCandidate(
        code=code,
        trading_date=TRADING_DATE,
        breakout_types=(
            HighBreakoutType.DAY_20,
            HighBreakoutType.DAY_60,
        ),
        close_price=3000.0,
        previous_20_day_high=2950.0,
        previous_60_day_high=2980.0,
        previous_year_high=2990.0,
        volume_ratio=volume_ratio,
        turnover=600_000_000.0,
        atr=60.0,
        atr_rate=0.02,
        score=score,
    )


def repository(
    tmp_path: Path,
) -> HighBreakoutCandidateRepository:
    database_path = tmp_path / "katana.db"
    initialize_database(database_path)

    return HighBreakoutCandidateRepository(
        database_path,
        now_provider=lambda: NOW,
    )


def test_initialize_database_creates_candidate_table(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "katana.db"
    initialize_database(database_path)

    with sqlite3.connect(database_path) as connection:
        table = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name = 'high_breakout_candidates'
            """
        ).fetchone()
        version = connection.execute(
            """
            SELECT version
            FROM schema_version
            WHERE id = 1
            """
        ).fetchone()

    assert table == (
        "high_breakout_candidates",
    )
    assert version == (
        SCHEMA_VERSION,
    )
    assert SCHEMA_VERSION == 13


def test_repository_saves_and_gets_candidate(
    tmp_path: Path,
) -> None:
    repo = repository(tmp_path)
    value = candidate()

    assert repo.save(value) == value
    assert repo.get(
        code="7203",
        trading_date=TRADING_DATE,
    ) == value
    assert repo.count() == 1


def test_repository_upserts_same_identity(
    tmp_path: Path,
) -> None:
    repo = repository(tmp_path)
    repo.save(candidate(score=70.0))
    repo.save(
        candidate(
            score=90.0,
            volume_ratio=3.0,
        )
    )

    loaded = repo.get(
        code="7203",
        trading_date=TRADING_DATE,
    )

    assert repo.count() == 1
    assert loaded.score == pytest.approx(
        90.0
    )
    assert loaded.volume_ratio == pytest.approx(
        3.0
    )


def test_repository_saves_many_and_orders_by_score(
    tmp_path: Path,
) -> None:
    repo = repository(tmp_path)

    assert repo.save_all(
        (
            candidate(
                code="7203",
                score=70.0,
            ),
            candidate(
                code="6758",
                score=90.0,
            ),
        )
    ) == 2

    values = repo.list_by_date(
        TRADING_DATE
    )

    assert [
        value.code
        for value in values
    ] == [
        "6758",
        "7203",
    ]


def test_repository_lists_recent_by_code(
    tmp_path: Path,
) -> None:
    repo = repository(tmp_path)
    repo.save(candidate())

    values = repo.list_recent(
        code="7203"
    )

    assert len(values) == 1
    assert values[0].code == "7203"


def test_repository_deletes_date(
    tmp_path: Path,
) -> None:
    repo = repository(tmp_path)
    repo.save_all(
        (
            candidate(code="7203"),
            candidate(code="6758"),
        )
    )

    assert repo.delete_date(
        TRADING_DATE
    ) == 2
    assert repo.count() == 0


def test_repository_rejects_missing_candidate(
    tmp_path: Path,
) -> None:
    repo = repository(tmp_path)

    with pytest.raises(
        HighBreakoutCandidateNotFoundError,
        match="存在しません",
    ):
        repo.get(
            code="7203",
            trading_date=TRADING_DATE,
        )


def test_repository_rejects_invalid_limit(
    tmp_path: Path,
) -> None:
    repo = repository(tmp_path)

    with pytest.raises(
        ValueError,
        match="取得件数",
    ):
        repo.list_recent(limit=0)
