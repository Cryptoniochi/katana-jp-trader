"""Sprint 125 Dynamic Watchlist explainability tests."""

from datetime import date
from pathlib import Path

from app.dynamic_watchlist.dynamic_watchlist_models import (
    DynamicWatchlistSettings,
)
from app.dynamic_watchlist.dynamic_watchlist_service import (
    DynamicWatchlistService,
)


def _service(tmp_path: Path) -> DynamicWatchlistService:
    return DynamicWatchlistService(
        database_path=tmp_path / "katana.db",
        watchlist_path=tmp_path / "watchlist.txt",
        report_directory=tmp_path / "reports",
        settings=DynamicWatchlistSettings(),
    )


def test_log_scale_accepts_zero_lower_bound(tmp_path: Path) -> None:
    service = _service(tmp_path)

    value = service._log_scale(
        1_000_000_000.0,
        lower=0.0,
        upper=5_000_000_000.0,
        maximum=20.0,
    )

    assert 0.0 <= value <= 20.0


def test_history_maturity_is_explainable(tmp_path: Path) -> None:
    service = _service(tmp_path)

    assert service._history_maturity_multiplier(
        history_days=10,
        full_history_days=20,
    ) == 0.80
    assert service._history_maturity_multiplier(
        history_days=15,
        full_history_days=20,
    ) == 0.90
    assert service._history_maturity_multiplier(
        history_days=20,
        full_history_days=20,
    ) == 1.0
