"""登録不能銘柄を分離してCollectorを継続できるか確認する。"""

from datetime import date, datetime, timezone
from pathlib import Path

from app.market.kabu_station_models import KabuStationSymbol
from app.universe.kabu_station_universe_daily_collector import (
    KabuStationUniverseDailyBarCollector,
)


NOW = datetime(2026, 8, 7, tzinfo=timezone.utc)


class FakeSettings:
    maximum_registered_symbols = 50


class FakeClient:
    settings = FakeSettings()

    def issue_token(self) -> str:
        return "token"

    def unregister_all(self) -> None:
        return None

    def register_symbols(
        self,
        symbols: tuple[KabuStationSymbol, ...],
    ):
        codes = tuple(item.code for item in symbols)

        if "2152" in codes:
            raise RuntimeError(
                "一部の銘柄が登録できませんでした"
            )

        return symbols

    def board(
        self,
        symbol: KabuStationSymbol,
    ):
        return {
            "OpeningPrice": 100.0,
            "HighPrice": 110.0,
            "LowPrice": 90.0,
            "CurrentPrice": 105.0,
            "TradingVolume": 1_000_000.0,
        }


def test_registration_failure_isolated_to_single_code(
    tmp_path: Path,
) -> None:
    collector = KabuStationUniverseDailyBarCollector(
        client=FakeClient(),
        database_path=tmp_path / "katana.db",
        request_interval_seconds=0,
        maximum_attempts=1,
        minimum_success_ratio=0.5,
        now_provider=lambda: NOW,
    )

    result = collector.collect(
        trading_date=date(2026, 8, 7),
        codes=(
            "2100",
            "2110",
            "2152",
            "2160",
            "2170",
        ),
    )

    assert result.requested_count == 5
    assert result.collected_count == 4
    assert result.saved_count == 4
    assert [item.code for item in result.failures] == [
        "2152"
    ]
