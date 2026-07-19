"""PaperTradingRuntimeFactory?????"""

from datetime import datetime, timezone
from pathlib import Path

from app.application.trading_loop_models import (
    TradingLoopCycleStatus,
)
from app.database import initialize_database
from app.runtime.paper_trading_runtime_factory import (
    PaperTradingRuntimeFactory,
)
from app.runtime.paper_trading_runtime_models import (
    PaperTradingRuntimeStatus,
)
from app.trading.portfolio_models import (
    PortfolioSnapshot,
)


NOW = datetime(
    2026,
    7,
    21,
    0,
    0,
    tzinfo=timezone.utc,
)


class FakeCycle:
    """????Trading Cycle???"""

    def __init__(
        self,
        cycle_number: int,
    ) -> None:
        """????????????"""

        self.cycle_number = cycle_number
        self.status = TradingLoopCycleStatus.COMPLETED
        self.error_message = None

    @property
    def is_successful(self) -> bool:
        """??????????"""

        return True

    @property
    def signal_count(self) -> int:
        """???????????"""

        return 1

    @property
    def execution_count(self) -> int:
        """???????"""

        return 1


class FakeCycleRunner:
    """????Trading Cycle Runner?"""

    def __init__(self) -> None:
        """???????????"""

        self.calls = 0

    def run_cycle(self) -> FakeCycle:
        """???Trading Cycle??????"""

        self.calls += 1

        return FakeCycle(
            self.calls
        )


class FakePortfolioReader:
    """????Portfolio Reader?"""

    def __init__(
        self,
        equities: tuple[float, ...],
    ) -> None:
        """??????????????"""

        self.equities = equities
        self.calls = 0

    def create_snapshot(
        self,
        *,
        generated_at: datetime | None = None,
    ) -> PortfolioSnapshot:
        """????Portfolio Snapshot????"""

        if generated_at is None:
            raise ValueError(
                "??????????"
            )

        equity = self.equities[
            self.calls
        ]
        self.calls += 1

        return PortfolioSnapshot(
            currency="JPY",
            cash_balance=equity,
            buying_power=equity,
            broker_market_value=0.0,
            broker_equity=equity,
            positions=(),
            generated_at=generated_at,
        )


def create_bundle(
    tmp_path: Path,
):
    """?????DB????Runtime Bundle??????"""

    database_path = (
        tmp_path / "katana.db"
    )

    initialize_database(
        database_path
    )

    bundle = PaperTradingRuntimeFactory.create(
        database_path=database_path,
        cycle_runner=FakeCycleRunner(),
        portfolio_reader=FakePortfolioReader(
            (
                1_000_000.0,
                1_005_000.0,
                1_005_000.0,
            )
        ),
        now_provider=lambda: NOW,
    )

    return database_path, bundle


def test_factory_creates_runtime_bundle(
    tmp_path: Path,
) -> None:
    """Runtime????Service????????"""

    database_path, bundle = create_bundle(
        tmp_path
    )

    assert (
        bundle.daily_repository.database_path
        == database_path
    )
    assert (
        bundle.runtime_persistence_service.runtime
        is bundle.runtime
    )
    assert (
        bundle.runtime_persistence_service
        .persistence_service
        is bundle.persistence_service
    )


def test_factory_bundle_runs_and_persists_summary(
    tmp_path: Path,
) -> None:
    """?????Runtime???????????????"""

    _database_path, bundle = create_bundle(
        tmp_path
    )

    bundle.runtime.start()
    record = bundle.runtime.run_cycle()

    result = (
        bundle.runtime_persistence_service
        .complete_and_persist()
    )

    summary = result.summary

    assert record.cycle_number == 1
    assert summary.status is (
        PaperTradingRuntimeStatus.COMPLETED
    )
    assert summary.cycle_count == 1
    assert summary.signal_count == 1
    assert summary.execution_count == 1
    assert summary.initial_equity == 1_000_000.0
    assert summary.final_equity == 1_005_000.0
    assert summary.net_profit_loss == 5_000.0

    assert bundle.daily_repository.count() == 1

    loaded = bundle.daily_repository.get(
        NOW.date()
    )

    assert loaded is not None
    assert loaded.status is (
        PaperTradingRuntimeStatus.COMPLETED
    )
    assert loaded.net_profit_loss == 5_000.0


def test_factory_bundle_persists_failed_runtime(
    tmp_path: Path,
) -> None:
    """?????????????????"""

    _database_path, bundle = create_bundle(
        tmp_path
    )

    bundle.runtime.start()

    result = (
        bundle.runtime_persistence_service
        .fail_and_persist(
            error_message="runtime failed"
        )
    )

    assert result.summary.status is (
        PaperTradingRuntimeStatus.FAILED
    )
    assert result.summary.error_message == (
        "runtime failed"
    )
    assert bundle.daily_repository.count() == 1
