"""Update persistent live peak equity from saved broker state only."""

from __future__ import annotations

from collections.abc import Callable

from app.live.kabu_station_read_only import KabuStationReadOnlySnapshot
from app.live.live_equity_peak_state import (
    LiveEquityPeakState,
    LiveEquityPeakStore,
)
from app.live.live_saved_equity import KabuStationSavedEquityCalculator


SnapshotProvider = Callable[[], KabuStationReadOnlySnapshot | None]


class LiveEquityPeakObserver:
    """Initialize or advance peak equity from saved live-account state only."""

    def __init__(
        self,
        *,
        snapshot_provider: SnapshotProvider,
        peak_store: LiveEquityPeakStore,
        calculator: KabuStationSavedEquityCalculator | None = None,
    ) -> None:
        self.snapshot_provider = snapshot_provider
        self.peak_store = peak_store
        self.calculator = calculator or KabuStationSavedEquityCalculator()

    def initialize(self) -> LiveEquityPeakState:
        """Explicitly create the first peak from a valid saved snapshot."""
        _, _, equity, _ = self.calculator(self.snapshot_provider())
        return self.peak_store.initialize(equity)

    def observe(self) -> LiveEquityPeakState:
        """Advance an already initialized peak from a valid saved snapshot."""
        _, _, equity, _ = self.calculator(self.snapshot_provider())
        return self.peak_store.observe(equity)
