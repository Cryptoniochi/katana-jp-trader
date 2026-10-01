"""Dynamic Watchlistの英字入り証券コード対応テスト。"""

from datetime import date
from pathlib import Path

import pytest

from app.dynamic_watchlist.dynamic_watchlist_service import (
    DynamicWatchlistService,
    _DailyBar,
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


@pytest.mark.parametrize("value", ("7203", "12345"))
def test_numeric_codes_are_paper_trading_compatible(
    value: str,
) -> None:
    validator = (
        DynamicWatchlistService.
        _is_paper_trading_compatible_symbol_code
    )
    assert validator(value) is True


@pytest.mark.parametrize("value", ("268A", "593A", "１２３４"))
def test_alphanumeric_codes_are_not_paper_trading_compatible(
    value: str,
) -> None:
    validator = (
        DynamicWatchlistService.
        _is_paper_trading_compatible_symbol_code
    )
    assert validator(value) is False


def test_alphanumeric_candidate_is_excluded_from_paper_watchlist(
    tmp_path: Path,
) -> None:
    service = DynamicWatchlistService(
        database_path=tmp_path / "katana.db",
        watchlist_path=tmp_path / "watchlist.txt",
        report_directory=tmp_path / "reports",
    )

    candidate = service._evaluate_code(
        code="268A",
        bars=[
            _DailyBar(
                trading_date=date(2026, 9, 30),
                open=1000.0,
                high=1010.0,
                low=990.0,
                close=1005.0,
                volume=1_000_000,
            )
        ],
        today=date(2026, 10, 1),
        learning_feedback=None,
    )

    assert (
        "unsupported_paper_trading_symbol_code"
        in candidate.exclusion_reasons
    )
