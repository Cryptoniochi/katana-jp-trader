"""kabuステーション候補ユニバース日足収集のテスト。"""

from datetime import date
from pathlib import Path

from app.universe.kabu_station_universe_daily_collector import (
    KabuStationUniverseDailyBarCollector,
)


class FakeClient:
    def __init__(self) -> None:
        self.token_issued = False

    def issue_token(self) -> str:
        self.token_issued = True
        return "token"

    def board(self, symbol):
        return {
            "OpeningPrice": 1000.0,
            "HighPrice": 1050.0,
            "LowPrice": 990.0,
            "CurrentPrice": 1030.0,
            "TradingVolume": 123456,
        }


class FakeRepository:
    def __init__(self) -> None:
        self.saved = ()

    def upsert_many(self, bars):
        self.saved = bars
        return len(bars)


def test_collects_and_saves_daily_bars(
    tmp_path: Path,
) -> None:
    client = FakeClient()
    repository = FakeRepository()
    collector = KabuStationUniverseDailyBarCollector(
        client=client,
        database_path=tmp_path / "katana.db",
        repository=repository,
        request_interval_seconds=0,
        sleeper=lambda _seconds: None,
    )

    result = collector.collect(
        trading_date=date(2026, 8, 6),
        codes=("7203", "8306"),
    )

    assert client.token_issued is True
    assert result.requested_count == 2
    assert result.collected_count == 2
    assert result.saved_count == 2
    assert result.success_ratio == 1.0
    assert len(repository.saved) == 2
    assert repository.saved[0].trading_date == date(
        2026, 8, 6
    )


def test_skips_symbol_without_trading_volume(
    tmp_path: Path,
) -> None:
    class NoTradeClient(FakeClient):
        def board(self, symbol):
            payload = super().board(symbol)
            payload["TradingVolume"] = 0
            return payload

    repository = FakeRepository()
    collector = KabuStationUniverseDailyBarCollector(
        client=NoTradeClient(),
        database_path=tmp_path / "katana.db",
        repository=repository,
        request_interval_seconds=0,
        minimum_success_ratio=0.5,
        sleeper=lambda _seconds: None,
    )

    try:
        collector.collect(
            trading_date=date(2026, 8, 6),
            codes=("7203",),
        )
    except RuntimeError as error:
        assert "成功率" in str(error)
    else:
        raise AssertionError(
            "成功率不足はRuntimeErrorである必要があります。"
        )
