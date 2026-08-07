"""Dynamic Watchlistの英字入り証券コード対応テスト。"""

from pathlib import Path

import pytest

from app.dynamic_watchlist.dynamic_watchlist_service import (
    DynamicWatchlistService,
)


@pytest.mark.parametrize(
    "value",
    (
        "7203",
        "130A",
        "607A",
        "12345",
    ),
)
def test_valid_symbol_codes_are_accepted(
    value: str,
) -> None:
    assert (
        DynamicWatchlistService._is_valid_symbol_code(
            value
        )
        is True
    )


@pytest.mark.parametrize(
    "value",
    (
        "",
        "123",
        "12-A",
        "ABCDEF",
        "１２３４",
    ),
)
def test_invalid_symbol_codes_are_rejected(
    value: str,
) -> None:
    assert (
        DynamicWatchlistService._is_valid_symbol_code(
            value
        )
        is False
    )


def test_candidate_universe_normalizes_alphanumeric_codes(
    tmp_path: Path,
) -> None:
    candidate_path = tmp_path / "candidates.txt"
    candidate_path.write_text(
        "7203\n130a\n607A\n",
        encoding="utf-8",
    )

    service = DynamicWatchlistService(
        database_path=tmp_path / "katana.db",
        watchlist_path=tmp_path / "watchlist.txt",
        report_directory=tmp_path / "reports",
        candidate_universe_path=candidate_path,
        require_candidate_universe=True,
    )

    assert service._load_candidate_universe() == {
        "7203",
        "130A",
        "607A",
    }


def test_required_candidate_universe_rejects_invalid_code(
    tmp_path: Path,
) -> None:
    candidate_path = tmp_path / "candidates.txt"
    candidate_path.write_text(
        "7203\n12-A\n",
        encoding="utf-8",
    )

    service = DynamicWatchlistService(
        database_path=tmp_path / "katana.db",
        watchlist_path=tmp_path / "watchlist.txt",
        report_directory=tmp_path / "reports",
        candidate_universe_path=candidate_path,
        require_candidate_universe=True,
    )

    with pytest.raises(
        RuntimeError,
        match="invalid symbols",
    ):
        service._load_candidate_universe()
