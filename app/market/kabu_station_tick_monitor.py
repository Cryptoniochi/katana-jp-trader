"""kabuステーションのリアルタイムTick受信診断。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from threading import Lock

from app.market.market_data_provider import MarketDataTick


@dataclass(frozen=True, slots=True)
class KabuStationTickMonitorStatus:
    """リアルタイムTick受信状況。"""

    received_tick_count: int
    received_codes: tuple[str, ...]
    last_tick: MarketDataTick | None
    first_received_at: datetime | None
    last_received_at: datetime | None


class KabuStationTickMonitor:
    """Tickを数え、必要に応じて標準出力へ表示する。"""

    def __init__(
        self,
        *,
        print_ticks: bool = True,
    ) -> None:
        """表示設定と初期状態を保持する。"""

        self.print_ticks = print_ticks
        self._received_tick_count = 0
        self._received_codes: set[str] = set()
        self._last_tick: MarketDataTick | None = None
        self._first_received_at: datetime | None = None
        self._last_received_at: datetime | None = None
        self._lock = Lock()

    def __call__(self, tick: MarketDataTick) -> None:
        """受信Tickを記録する。"""

        with self._lock:
            self._received_tick_count += 1
            self._received_codes.add(tick.code)
            self._last_tick = tick

            if self._first_received_at is None:
                self._first_received_at = tick.observed_at

            self._last_received_at = tick.observed_at

            if self.print_ticks:
                volume = (
                    "-"
                    if tick.cumulative_volume is None
                    else f"{tick.cumulative_volume:g}"
                )
                print(
                    "TICK "
                    f"code={tick.code} "
                    f"time={tick.observed_at.isoformat()} "
                    f"price={tick.price:g} "
                    f"cumulative_volume={volume}"
                )

    def status(self) -> KabuStationTickMonitorStatus:
        """現在の受信状況を返す。"""

        with self._lock:
            return KabuStationTickMonitorStatus(
                received_tick_count=(
                    self._received_tick_count
                ),
                received_codes=tuple(
                    sorted(self._received_codes)
                ),
                last_tick=self._last_tick,
                first_received_at=self._first_received_at,
                last_received_at=self._last_received_at,
            )
