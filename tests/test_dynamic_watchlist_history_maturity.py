"""Dynamic Watchlistの履歴成熟度評価テスト。"""

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from app.dynamic_watchlist.dynamic_watchlist_models import (
    DynamicWatchlistSettings,
)
from app.dynamic_watchlist.dynamic_watchlist_service import (
    DynamicWatchlistService,
    _DailyBar,
)


TODAY = date(2026, 8, 10)


def _bars(
    count: int,
    *,
    close: float = 1000.0,
    daily_move: float = 0.01,
) -> list[_DailyBar]:
    start = TODAY - timedelta(days=count - 1)
    result = []

    for index in range(count):
        price = close * (
            1.0 + daily_move * index / max(count, 1)
        )
        result.append(
            _DailyBar(
                trading_date=start + timedelta(days=index),
                open=price * 0.99,
                high=price * 1.03,
                low=price * 0.97,
                close=price,
                volume=1_000_000,
            )
        )

    return result


def _service(
    tmp_path: Path,
) -> DynamicWatchlistService:
    # _log_scale() は対数スケールを使うため、下限値は必ず正数にする。
    # 実運用設定と同じ前提をテストfixtureでも守る。
    settings = DynamicWatchlistSettings(
        capital_limit=10_000_000,
        purchase_budget=10_000_000,
        minimum_history_days=20,
        fallback_minimum_history_days=1,
        minimum_average_volume=1,
        minimum_average_turnover=1_000_000,
        fallback_minimum_average_volume=1,
        fallback_minimum_average_turnover=1_000_000,
        maximum_data_age_days=10,
        fallback_maximum_data_age_days=10,
        minimum_symbols=1,
        maximum_symbols=50,
    )
    return DynamicWatchlistService(
        database_path=tmp_path / "katana.db",
        watchlist_path=tmp_path / "watchlist.txt",
        report_directory=tmp_path / "reports",
        settings=settings,
        now_provider=lambda: datetime(
            2026,
            8,
            10,
            tzinfo=timezone.utc,
        ),
    )


def test_history_maturity_multiplier() -> None:
    multiplier = (
        DynamicWatchlistService
        ._history_maturity_multiplier
    )

    assert multiplier(
        history_days=10,
        full_history_days=20,
    ) == 0.80
    assert multiplier(
        history_days=15,
        full_history_days=20,
    ) == 0.90
    assert multiplier(
        history_days=20,
        full_history_days=20,
    ) == 1.00
    assert multiplier(
        history_days=30,
        full_history_days=20,
    ) == 1.00


def test_nine_days_keeps_legacy_fallback_behavior(
    tmp_path: Path,
) -> None:
    candidate = _service(
        tmp_path
    )._evaluate_code(
        code="1234",
        bars=_bars(9),
        today=TODAY,
        learning_feedback=None,
    )

    assert candidate.selection_tier == "fallback"
    assert "insufficient_history" not in (
        candidate.exclusion_reasons
    )


def test_ten_days_is_developing_and_eligible(
    tmp_path: Path,
) -> None:
    candidate = _service(
        tmp_path
    )._evaluate_code(
        code="1234",
        bars=_bars(10),
        today=TODAY,
        learning_feedback=None,
    )

    assert candidate.selection_tier == "developing"
    assert "insufficient_history" not in (
        candidate.exclusion_reasons
    )
    assert candidate.total_score == round(
        candidate.technical_score * 0.80,
        4,
    )


def test_fifteen_days_receives_smaller_penalty(
    tmp_path: Path,
) -> None:
    candidate = _service(
        tmp_path
    )._evaluate_code(
        code="1234",
        bars=_bars(15),
        today=TODAY,
        learning_feedback=None,
    )

    assert candidate.selection_tier == "developing"
    assert candidate.total_score == round(
        candidate.technical_score * 0.90,
        4,
    )


def test_twenty_days_is_full_strength(
    tmp_path: Path,
) -> None:
    candidate = _service(
        tmp_path
    )._evaluate_code(
        code="1234",
        bars=_bars(20),
        today=TODAY,
        learning_feedback=None,
    )

    assert candidate.selection_tier == "strict"
    assert candidate.total_score == (
        candidate.technical_score
    )
