"""Sprint 125 quality-first watchlist apply regression tests."""

from datetime import date
from pathlib import Path
from types import SimpleNamespace

from app.dynamic_watchlist.dynamic_watchlist_service import (
    DynamicWatchlistService,
)


def _candidate(code: str):
    return SimpleNamespace(code=code)


def test_apply_watchlist_accepts_fewer_than_legacy_minimum(
    tmp_path: Path,
) -> None:
    service = DynamicWatchlistService(
        database_path=tmp_path / "katana.db",
        watchlist_path=tmp_path / "watchlist.txt",
        report_directory=tmp_path / "reports",
    )

    service._apply_watchlist(
        selected=(
            _candidate("8306"),
            _candidate("6758"),
            _candidate("9432"),
        ),
        target_date=date(2026, 8, 11),
    )

    assert (
        service.watchlist_path.read_text(
            encoding="utf-8"
        ).splitlines()
        == ["8306", "6758", "9432"]
    )


def test_apply_watchlist_rejects_empty_selection(
    tmp_path: Path,
) -> None:
    service = DynamicWatchlistService(
        database_path=tmp_path / "katana.db",
        watchlist_path=tmp_path / "watchlist.txt",
        report_directory=tmp_path / "reports",
    )

    try:
        service._apply_watchlist(
            selected=(),
            target_date=date(2026, 8, 11),
        )
    except RuntimeError as error:
        assert str(error) == (
            "Generated watchlist validation failed."
        )
    else:
        raise AssertionError(
            "empty watchlist must be rejected"
        )
