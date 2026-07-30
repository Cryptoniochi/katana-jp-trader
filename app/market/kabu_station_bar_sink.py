"""kabuステーション5分足を既存Repositoryへ保存する。"""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock

from app.market.bar_repository import MarketBarRepository
from app.market.models import StockPrice
from app.market.realtime_bar_aggregator import RealtimeBar


@dataclass(frozen=True, slots=True)
class KabuStationBarSinkStatus:
    """Repository保存状況。"""

    received_bar_count: int
    saved_bar_count: int
    last_saved_bar: StockPrice | None
    last_error: str | None = None


class KabuStationBarRepositorySink:
    """RealtimeBarをStockPriceへ変換してSQLiteへ保存する。"""

    def __init__(
        self,
        *,
        repository: MarketBarRepository,
        interval_minutes: int = 5,
        data_source: str = "kabu-station-realtime",
    ) -> None:
        """保存先とデータソースを保持する。"""

        normalized_source = data_source.strip()

        if interval_minutes <= 0:
            raise ValueError(
                "足間隔は0より大きい必要があります。"
            )

        if not normalized_source:
            raise ValueError(
                "データソースを指定してください。"
            )

        self.repository = repository
        self.interval_minutes = interval_minutes
        self.data_source = normalized_source
        self._received_bar_count = 0
        self._saved_bar_count = 0
        self._last_saved_bar: StockPrice | None = None
        self._last_error: str | None = None
        self._lock = Lock()

    def __call__(self, bar: RealtimeBar) -> None:
        """完成バーを保存する。"""

        stock_price = StockPrice(
            code=bar.code,
            datetime=bar.started_at,
            open=bar.open_price,
            high=bar.high_price,
            low=bar.low_price,
            close=bar.close_price,
            volume=max(0, int(round(bar.volume))),
        )

        with self._lock:
            self._received_bar_count += 1

            try:
                saved_count = self.repository.save_all(
                    [stock_price],
                    interval_minutes=self.interval_minutes,
                    data_source=self.data_source,
                )
            except Exception as error:
                self._last_error = (
                    str(error).strip()
                    or type(error).__name__
                )
                raise

            self._saved_bar_count += saved_count
            self._last_saved_bar = stock_price
            self._last_error = None

    def status(self) -> KabuStationBarSinkStatus:
        """現在の保存状況を返す。"""

        with self._lock:
            return KabuStationBarSinkStatus(
                received_bar_count=(
                    self._received_bar_count
                ),
                saved_bar_count=self._saved_bar_count,
                last_saved_bar=self._last_saved_bar,
                last_error=self._last_error,
            )
