"""EquityCurveServiceのテスト。"""

from datetime import datetime, timedelta, timezone

import pytest

from app.trading.equity_curve_service import (
    EquityCurveService,
)
from app.trading.portfolio_models import PortfolioSnapshot


BASE_TIME = datetime(
    2026,
    7,
    20,
    1,
    0,
    tzinfo=timezone.utc,
)


def create_snapshot(
    *,
    minute: int,
    cash_balance: float,
    market_value: float,
    realized_profit_loss: float = 0.0,
    unrealized_profit_loss: float = 0.0,
) -> PortfolioSnapshot:
    """テスト用ポートフォリオSnapshotを作成する。"""

    equity = cash_balance + market_value

    return PortfolioSnapshot(
        currency="JPY",
        cash_balance=cash_balance,
        buying_power=cash_balance,
        broker_market_value=market_value,
        broker_equity=equity,
        positions=(),
        generated_at=(
            BASE_TIME
            + timedelta(minutes=minute)
        ),
    )


class FakePortfolioRepository:
    """固定履歴を新しい順に返すRepository。"""

    def __init__(
        self,
        snapshots: list[PortfolioSnapshot],
    ) -> None:
        self.snapshots = snapshots
        self.requested_limit: int | None = None

    def list_recent(
        self,
        *,
        limit: int = 100,
    ) -> list[PortfolioSnapshot]:
        self.requested_limit = limit

        return sorted(
            self.snapshots,
            key=lambda item: item.generated_at,
            reverse=True,
        )[:limit]


def test_service_creates_equity_curve_in_time_order() -> None:
    """新しい順の履歴を古い順の資産曲線へ変換する。"""

    snapshots = [
        create_snapshot(
            minute=0,
            cash_balance=1_000_000.0,
            market_value=0.0,
        ),
        create_snapshot(
            minute=1,
            cash_balance=750_000.0,
            market_value=260_000.0,
        ),
        create_snapshot(
            minute=2,
            cash_balance=760_000.0,
            market_value=250_000.0,
        ),
    ]
    repository = FakePortfolioRepository(snapshots)
    service = EquityCurveService(
        portfolio_repository=repository
    )

    report = service.create_report()

    assert report.point_count == 3
    assert report.period_count == 2
    assert [
        point.generated_at
        for point in report.points
    ] == [
        BASE_TIME,
        BASE_TIME + timedelta(minutes=1),
        BASE_TIME + timedelta(minutes=2),
    ]

    assert report.initial_equity == pytest.approx(
        1_000_000.0
    )
    assert report.final_equity == pytest.approx(
        1_010_000.0
    )
    assert report.absolute_profit_loss == pytest.approx(
        10_000.0
    )
    assert report.total_return == pytest.approx(0.01)


def test_service_calculates_period_and_cumulative_returns() -> None:
    """期間収益率と累積収益率を計算する。"""

    repository = FakePortfolioRepository(
        [
            create_snapshot(
                minute=0,
                cash_balance=1_000_000.0,
                market_value=0.0,
            ),
            create_snapshot(
                minute=1,
                cash_balance=1_100_000.0,
                market_value=0.0,
            ),
            create_snapshot(
                minute=2,
                cash_balance=990_000.0,
                market_value=0.0,
            ),
        ]
    )
    report = EquityCurveService(
        portfolio_repository=repository
    ).create_report()

    assert report.points[0].period_return is None
    assert report.points[1].period_return == pytest.approx(
        0.10
    )
    assert report.points[2].period_return == pytest.approx(
        -0.10
    )
    assert report.points[2].cumulative_return == pytest.approx(
        -0.01
    )
    assert report.winning_period_count == 1
    assert report.losing_period_count == 1
    assert report.flat_period_count == 0
    assert report.winning_period_rate == pytest.approx(
        0.5
    )


def test_service_calculates_maximum_drawdown() -> None:
    """ピークからの最大ドローダウンを計算する。"""

    repository = FakePortfolioRepository(
        [
            create_snapshot(
                minute=0,
                cash_balance=1_000_000.0,
                market_value=0.0,
            ),
            create_snapshot(
                minute=1,
                cash_balance=1_200_000.0,
                market_value=0.0,
            ),
            create_snapshot(
                minute=2,
                cash_balance=900_000.0,
                market_value=0.0,
            ),
            create_snapshot(
                minute=3,
                cash_balance=1_100_000.0,
                market_value=0.0,
            ),
        ]
    )

    report = EquityCurveService(
        portfolio_repository=repository
    ).create_report()

    assert report.maximum_drawdown_amount == pytest.approx(
        300_000.0
    )
    assert report.maximum_drawdown == pytest.approx(
        0.25
    )


def test_service_counts_flat_periods() -> None:
    """純資産が変わらない期間を横ばいとして数える。"""

    snapshot = create_snapshot(
        minute=0,
        cash_balance=1_000_000.0,
        market_value=0.0,
    )
    later = create_snapshot(
        minute=1,
        cash_balance=1_000_000.0,
        market_value=0.0,
    )

    report = EquityCurveService(
        portfolio_repository=(
            FakePortfolioRepository(
                [snapshot, later]
            )
        )
    ).create_report()

    assert report.flat_period_count == 1
    assert report.winning_period_rate is None


def test_service_returns_empty_report_without_history() -> None:
    """履歴がなければゼロ値の空レポートを返す。"""

    report = EquityCurveService(
        portfolio_repository=(
            FakePortfolioRepository([])
        )
    ).create_report()

    assert report.points == ()
    assert report.point_count == 0
    assert report.period_count == 0
    assert report.initial_equity == 0.0
    assert report.final_equity == 0.0
    assert report.total_return == 0.0
    assert report.maximum_drawdown == 0.0
    assert report.winning_period_rate is None


def test_service_passes_limit_to_repository() -> None:
    """取得件数をRepositoryへ渡す。"""

    repository = FakePortfolioRepository(
        [
            create_snapshot(
                minute=0,
                cash_balance=1_000_000.0,
                market_value=0.0,
            )
        ]
    )
    service = EquityCurveService(
        portfolio_repository=repository
    )

    service.create_report(limit=25)

    assert repository.requested_limit == 25


def test_service_rejects_invalid_limit() -> None:
    """0以下の取得件数を拒否する。"""

    service = EquityCurveService(
        portfolio_repository=(
            FakePortfolioRepository([])
        )
    )

    with pytest.raises(ValueError, match="取得件数"):
        service.create_report(limit=0)
