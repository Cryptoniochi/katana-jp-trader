"""??Paper Trading Runtime????????????"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

from app.runtime.paper_trading_daily_repository import (
    PaperTradingDailySummaryRepository,
)
from app.runtime.paper_trading_persistence_service import (
    PaperTradingPersistenceService,
)
from app.runtime.paper_trading_runtime import (
    PaperTradingRuntime,
)
from app.runtime.paper_trading_runtime_persistence import (
    PaperTradingRuntimePersistenceService,
)


class PaperTradingRuntimeCycleRunner(Protocol):
    """Factory?????Trading Cycle?????"""

    def run_cycle(self):
        """Trading Cycle?1??????"""


class PaperTradingRuntimePortfolioReader(Protocol):
    """Factory?????Portfolio?????"""

    def create_snapshot(
        self,
        *,
        generated_at: datetime | None = None,
    ):
        """???Portfolio Snapshot????"""


@dataclass(frozen=True, slots=True)
class PaperTradingRuntimeBundle:
    """??????Paper Trading Runtime???"""

    runtime: PaperTradingRuntime
    daily_repository: PaperTradingDailySummaryRepository
    persistence_service: PaperTradingPersistenceService
    runtime_persistence_service: (
        PaperTradingRuntimePersistenceService
    )


class PaperTradingRuntimeFactory:
    """??Paper Trading Runtime????????"""

    @staticmethod
    def create(
        *,
        database_path: Path,
        cycle_runner: PaperTradingRuntimeCycleRunner,
        portfolio_reader: PaperTradingRuntimePortfolioReader,
        now_provider: Callable[[], datetime] | None = None,
    ) -> PaperTradingRuntimeBundle:
        """??Component??Runtime????????????"""

        resolved_database_path = Path(
            database_path
        )

        runtime = PaperTradingRuntime(
            cycle_runner=cycle_runner,
            portfolio_reader=portfolio_reader,
            now_provider=now_provider,
        )

        daily_repository = (
            PaperTradingDailySummaryRepository(
                resolved_database_path,
                now_provider=now_provider,
            )
        )

        persistence_service = (
            PaperTradingPersistenceService(
                daily_repository=daily_repository
            )
        )

        runtime_persistence_service = (
            PaperTradingRuntimePersistenceService(
                runtime=runtime,
                persistence_service=persistence_service,
            )
        )

        return PaperTradingRuntimeBundle(
            runtime=runtime,
            daily_repository=daily_repository,
            persistence_service=persistence_service,
            runtime_persistence_service=(
                runtime_persistence_service
            ),
        )
