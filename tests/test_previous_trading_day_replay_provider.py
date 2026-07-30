"""前営業日リプレイProviderのテスト。"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from app.market.models import StockPrice
from app.market.previous_trading_day_replay_provider import (
    PreviousTradingDayReplayProvider,
)


JST = ZoneInfo("Asia/Tokyo")


class FakeDownloader:
    """取得要求を記録するDownloader。"""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def download(
        self,
        code: str,
        date: str,
    ) -> list[StockPrice]:
        self.calls.append((code, date))

        return [
            StockPrice(
                code=code,
                datetime=datetime(
                    2026,
                    7,
                    28,
                    9,
                    0,
                    tzinfo=JST,
                ),
                open=1000.0,
                high=1010.0,
                low=990.0,
                close=1005.0,
                volume=1000,
            )
        ]


class FakeAggregator:
    """入力をそのまま返すAggregator。"""

    def aggregate_to_five_minutes(
        self,
        prices: list[StockPrice],
    ) -> list[StockPrice]:
        return list(prices)


def test_provider_downloads_previous_trading_day_and_shifts_date() -> None:
    """前営業日の足を対象日の同時刻へ移す。"""

    downloader = FakeDownloader()
    provider = PreviousTradingDayReplayProvider(
        downloader=downloader,
        aggregator=FakeAggregator(),
        trading_day_predicate=lambda value: (
            value.weekday() < 5
        ),
    )

    prices = provider(
        "7203",
        date(2026, 7, 29),
    )

    assert downloader.calls == [
        ("7203", "2026-07-28")
    ]
    assert len(prices) == 1
    assert prices[0].datetime == datetime(
        2026,
        7,
        29,
        9,
        0,
        tzinfo=JST,
    )
    assert prices[0].close == 1005.0
    assert provider.source_date(
        "7203",
        date(2026, 7, 29),
    ) == date(2026, 7, 28)


def test_provider_skips_weekend() -> None:
    """月曜日は直前の金曜日を使用する。"""

    downloader = FakeDownloader()
    provider = PreviousTradingDayReplayProvider(
        downloader=downloader,
        aggregator=FakeAggregator(),
        trading_day_predicate=lambda value: (
            value.weekday() < 5
        ),
    )

    provider(
        "7203",
        date(2026, 8, 3),
    )

    assert downloader.calls == [
        ("7203", "2026-07-31")
    ]


def test_provider_caches_by_code_and_target_date() -> None:
    """同じ銘柄・対象日は再取得しない。"""

    downloader = FakeDownloader()
    provider = PreviousTradingDayReplayProvider(
        downloader=downloader,
        aggregator=FakeAggregator(),
        trading_day_predicate=lambda _value: True,
    )

    first = provider(
        "7203",
        date(2026, 7, 29),
    )
    second = provider(
        "7203",
        date(2026, 7, 29),
    )

    assert first == second
    assert len(downloader.calls) == 1


def test_provider_rejects_invalid_lookback() -> None:
    """不正な最大遡及日数を拒否する。"""

    with pytest.raises(ValueError, match="最大遡及"):
        PreviousTradingDayReplayProvider(
            downloader=FakeDownloader(),
            aggregator=FakeAggregator(),
            trading_day_predicate=lambda _value: True,
            maximum_lookback_days=0,
        )


def test_provider_raises_when_previous_day_is_unavailable() -> None:
    """期間内に取引日がなければ失敗する。"""

    provider = PreviousTradingDayReplayProvider(
        downloader=FakeDownloader(),
        aggregator=FakeAggregator(),
        trading_day_predicate=lambda _value: False,
        maximum_lookback_days=2,
    )

    with pytest.raises(RuntimeError, match="前営業日"):
        provider(
            "7203",
            date(2026, 7, 29),
        )


def test_provider_diagnostics_count_download_and_cache_hit() -> None:
    """取得回数・足数・キャッシュ利用を診断できる。"""

    downloader = FakeDownloader()
    provider = PreviousTradingDayReplayProvider(
        downloader=downloader,
        aggregator=FakeAggregator(),
        trading_day_predicate=lambda _value: True,
    )

    provider("7203", date(2026, 7, 29))
    provider("7203", date(2026, 7, 29))

    snapshot = provider.diagnostic_snapshot()

    assert snapshot.request_count == 2
    assert snapshot.download_count == 1
    assert snapshot.cache_hit_count == 1
    assert snapshot.cache_hit_rate == pytest.approx(0.5)
    assert snapshot.downloaded_minute_bar_count == 1
    assert snapshot.generated_five_minute_bar_count == 1
    assert snapshot.source_dates == (date(2026, 7, 28),)
    assert snapshot.target_dates == (date(2026, 7, 29),)
    assert snapshot.symbol_count == 1


def test_clear_cache_resets_replay_diagnostics() -> None:
    """キャッシュ破棄時に診断値も初期化する。"""

    provider = PreviousTradingDayReplayProvider(
        downloader=FakeDownloader(),
        aggregator=FakeAggregator(),
        trading_day_predicate=lambda _value: True,
    )
    provider("7203", date(2026, 7, 29))

    provider.clear_cache()

    snapshot = provider.diagnostic_snapshot()
    assert snapshot.request_count == 0
    assert snapshot.download_count == 0
    assert snapshot.source_dates == ()
