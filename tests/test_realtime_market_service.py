"""リアルタイム市場監視基盤のテスト。"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from app.market.jquants_downloader import JQuantsDownloadError
from app.market.models import StockPrice
from app.market.realtime_market_service import (
    JST,
    RealtimeMarketMonitor,
    TokyoMarketSessionService,
)
from app.market.realtime_models import (
    MarketSessionState,
    RealtimePollDecision,
)


UTC = ZoneInfo("UTC")


class FakeRepository:
    """監視サービス用の簡易Repository。"""

    def __init__(
        self,
        latest_by_code: dict[str, datetime | None] | None = None,
    ) -> None:
        self.latest_by_code = latest_by_code or {}
        self.saved: list[StockPrice] = []

    def latest_datetime(
        self,
        code: str,
        interval_minutes: int,
    ) -> datetime | None:
        assert interval_minutes == 5
        return self.latest_by_code.get(code)

    def save_all(
        self,
        prices: list[StockPrice],
        interval_minutes: int,
        data_source: str,
    ) -> int:
        assert interval_minutes == 5
        assert data_source == "realtime-test"
        self.saved.extend(prices)
        return len(prices)


def price(
    code: str,
    hour: int,
    minute: int,
) -> StockPrice:
    """テスト用5分足を作成する。"""

    return StockPrice(
        code=code,
        datetime=datetime(
            2026,
            7,
            17,
            hour,
            minute,
            tzinfo=JST,
        ),
        open=1000.0,
        high=1010.0,
        low=990.0,
        close=1005.0,
        volume=1000,
    )


@pytest.mark.parametrize(
    ("hour", "minute", "expected"),
    [
        (8, 59, MarketSessionState.PRE_OPEN),
        (9, 0, MarketSessionState.MORNING),
        (11, 29, MarketSessionState.MORNING),
        (11, 30, MarketSessionState.LUNCH_BREAK),
        (12, 29, MarketSessionState.LUNCH_BREAK),
        (12, 30, MarketSessionState.AFTERNOON),
        (15, 29, MarketSessionState.AFTERNOON),
        (15, 30, MarketSessionState.POST_CLOSE),
    ],
)
def test_session_service_resolves_market_state(
    hour: int,
    minute: int,
    expected: MarketSessionState,
) -> None:
    """東京市場の時刻境界を判定する。"""

    snapshot = TokyoMarketSessionService(
        trading_day_predicate=lambda _date: True
    ).create_snapshot(
        datetime(
            2026,
            7,
            17,
            hour,
            minute,
            tzinfo=JST,
        )
    )

    assert snapshot.state is expected
    assert snapshot.is_trading is expected.is_trading


def test_session_service_converts_utc_to_jst() -> None:
    """監視時刻を日本時間へ変換する。"""

    snapshot = TokyoMarketSessionService(
        trading_day_predicate=lambda _date: True
    ).create_snapshot(
        datetime(
            2026,
            7,
            17,
            0,
            0,
            tzinfo=UTC,
        )
    )

    assert snapshot.observed_at.hour == 9
    assert snapshot.observed_at.tzinfo == JST
    assert snapshot.state is MarketSessionState.MORNING


def test_session_service_marks_non_trading_day_closed() -> None:
    """休日は時刻に関係なくclosedにする。"""

    snapshot = TokyoMarketSessionService(
        trading_day_predicate=lambda _date: False
    ).create_snapshot(
        datetime(
            2026,
            7,
            18,
            10,
            0,
            tzinfo=JST,
        )
    )

    assert snapshot.state is MarketSessionState.CLOSED
    assert snapshot.is_trading_day is False
    assert snapshot.is_trading is False


def test_monitor_idles_on_non_trading_day() -> None:
    """休日はProviderへアクセスせず待機する。"""

    called = False

    def provider(
        _code: str,
        _target_date: date,
    ) -> list[StockPrice]:
        nonlocal called
        called = True
        return []

    result = RealtimeMarketMonitor(
        repository=FakeRepository(),
        bar_provider=provider,
        session_service=TokyoMarketSessionService(
            trading_day_predicate=lambda _date: False
        ),
        data_source="realtime-test",
    ).poll(
        codes=("7203",),
        observed_at=datetime(
            2026,
            7,
            18,
            10,
            0,
            tzinfo=JST,
        ),
    )

    assert result.decision is (
        RealtimePollDecision.IDLE_NON_TRADING_DAY
    )
    assert called is False
    assert result.fetched_bar_count == 0


def test_monitor_idles_outside_market_hours() -> None:
    """取引日の時間外はProviderへアクセスしない。"""

    called = False

    def provider(
        _code: str,
        _target_date: date,
    ) -> list[StockPrice]:
        nonlocal called
        called = True
        return []

    result = RealtimeMarketMonitor(
        repository=FakeRepository(),
        bar_provider=provider,
        session_service=TokyoMarketSessionService(
            trading_day_predicate=lambda _date: True
        ),
        data_source="realtime-test",
    ).poll(
        codes=("7203",),
        observed_at=datetime(
            2026,
            7,
            17,
            8,
            30,
            tzinfo=JST,
        ),
    )

    assert result.decision is (
        RealtimePollDecision.IDLE_OUTSIDE_MARKET_HOURS
    )
    assert called is False


def test_monitor_saves_only_new_completed_bars() -> None:
    """保存済みより新しく、確定済みの足だけ保存する。"""

    repository = FakeRepository(
        {
            "7203": datetime(
                2026,
                7,
                17,
                9,
                0,
                tzinfo=JST,
            )
        }
    )

    result = RealtimeMarketMonitor(
        repository=repository,
        bar_provider=lambda _code, _date: [
            price("7203", 9, 0),
            price("7203", 9, 5),
            price("7203", 9, 10),
            price("7203", 9, 15),
        ],
        session_service=TokyoMarketSessionService(
            trading_day_predicate=lambda _date: True
        ),
        data_source="realtime-test",
    ).poll(
        codes=("7203",),
        observed_at=datetime(
            2026,
            7,
            17,
            9,
            17,
            tzinfo=JST,
        ),
    )

    assert result.decision is (
        RealtimePollDecision.NEW_BARS_SAVED
    )
    assert result.fetched_bar_count == 4
    assert result.new_bar_count == 2
    assert result.saved_bar_count == 2
    assert [
        item.datetime.minute
        for item in repository.saved
    ] == [5, 10]


def test_monitor_prevents_duplicates_from_provider() -> None:
    """Provider内の同一開始日時重複を除去する。"""

    duplicate = price("7203", 9, 5)
    repository = FakeRepository()

    result = RealtimeMarketMonitor(
        repository=repository,
        bar_provider=lambda _code, _date: [
            duplicate,
            duplicate,
        ],
        session_service=TokyoMarketSessionService(
            trading_day_predicate=lambda _date: True
        ),
        data_source="realtime-test",
    ).poll(
        codes=("7203",),
        observed_at=datetime(
            2026,
            7,
            17,
            9,
            11,
            tzinfo=JST,
        ),
    )

    assert result.new_bar_count == 1
    assert result.saved_bar_count == 1
    assert len(repository.saved) == 1


def test_monitor_returns_no_new_bar() -> None:
    """全足が保存済みなら保存処理を行わない。"""

    repository = FakeRepository(
        {
            "7203": datetime(
                2026,
                7,
                17,
                9,
                5,
                tzinfo=JST,
            )
        }
    )

    result = RealtimeMarketMonitor(
        repository=repository,
        bar_provider=lambda _code, _date: [
            price("7203", 9, 0),
            price("7203", 9, 5),
        ],
        session_service=TokyoMarketSessionService(
            trading_day_predicate=lambda _date: True
        ),
        data_source="realtime-test",
    ).poll(
        codes=("7203",),
        observed_at=datetime(
            2026,
            7,
            17,
            9,
            20,
            tzinfo=JST,
        ),
    )

    assert result.decision is RealtimePollDecision.NO_NEW_BAR
    assert result.saved_bar_count == 0
    assert repository.saved == []


def test_monitor_supports_multiple_codes_and_removes_code_duplicates() -> None:
    """複数銘柄を処理し、入力コード重複を除去する。"""

    repository = FakeRepository()

    def provider(
        code: str,
        _target_date: date,
    ) -> list[StockPrice]:
        return [price(code, 9, 0)]

    result = RealtimeMarketMonitor(
        repository=repository,
        bar_provider=provider,
        session_service=TokyoMarketSessionService(
            trading_day_predicate=lambda _date: True
        ),
        data_source="realtime-test",
    ).poll(
        codes=("7203", "6758", "7203"),
        observed_at=datetime(
            2026,
            7,
            17,
            9,
            6,
            tzinfo=JST,
        ),
    )

    assert result.code_count == 2
    assert result.new_bar_count == 2
    assert {
        item.code
        for item in result.new_bars
    } == {"7203", "6758"}


def test_monitor_rejects_provider_code_mismatch() -> None:
    """要求銘柄と異なるProvider応答を拒否する。"""

    monitor = RealtimeMarketMonitor(
        repository=FakeRepository(),
        bar_provider=lambda _code, _date: [
            price("6758", 9, 0)
        ],
        session_service=TokyoMarketSessionService(
            trading_day_predicate=lambda _date: True
        ),
        data_source="realtime-test",
    )

    with pytest.raises(ValueError, match="異なる"):
        monitor.poll(
            codes=("7203",),
            observed_at=datetime(
                2026,
                7,
                17,
                9,
                6,
                tzinfo=JST,
            ),
        )


def test_monitor_rejects_empty_codes() -> None:
    """空の監視対象を拒否する。"""

    monitor = RealtimeMarketMonitor(
        repository=FakeRepository(),
        bar_provider=lambda _code, _date: [],
        data_source="realtime-test",
    )

    with pytest.raises(ValueError, match="1件以上"):
        monitor.poll(
            codes=(),
            observed_at=datetime.now(JST),
        )


def test_session_service_rejects_naive_datetime() -> None:
    """タイムゾーンなし監視日時を拒否する。"""

    with pytest.raises(ValueError, match="タイムゾーン"):
        TokyoMarketSessionService().create_snapshot(
            datetime(2026, 7, 17, 9, 0)
        )



def test_monitor_limits_codes_and_rotates_round_robin() -> None:
    """取得上限に従い監視銘柄を順番に巡回する。"""

    requested: list[str] = []

    def provider(
        code: str,
        _target_date: date,
    ) -> list[StockPrice]:
        requested.append(code)
        return []

    monitor = RealtimeMarketMonitor(
        repository=FakeRepository(),
        bar_provider=provider,
        session_service=TokyoMarketSessionService(
            trading_day_predicate=lambda _date: True
        ),
        data_source="realtime-test",
        maximum_codes_per_poll=2,
    )
    codes = ("1001", "1002", "1003", "1004", "1005")

    for minute in (1, 2, 3):
        monitor.poll(
            codes=codes,
            observed_at=datetime(
                2026,
                7,
                17,
                9,
                minute,
                tzinfo=JST,
            ),
        )

    assert requested == [
        "1001",
        "1002",
        "1003",
        "1004",
        "1005",
        "1001",
    ]


def test_monitor_enters_cooldown_after_rate_limit() -> None:
    """429後は指定時間Provider呼び出しを停止する。"""

    call_count = 0

    def provider(
        _code: str,
        _target_date: date,
    ) -> list[StockPrice]:
        nonlocal call_count
        call_count += 1

        if call_count == 1:
            raise JQuantsDownloadError(
                "rate limited",
                status_code=429,
                retry_after_seconds=60.0,
            )

        return []

    monitor = RealtimeMarketMonitor(
        repository=FakeRepository(),
        bar_provider=provider,
        session_service=TokyoMarketSessionService(
            trading_day_predicate=lambda _date: True
        ),
        data_source="realtime-test",
        maximum_codes_per_poll=1,
        rate_limit_cooldown_seconds=30.0,
    )

    first = monitor.poll(
        codes=("7203",),
        observed_at=datetime(
            2026,
            7,
            17,
            9,
            0,
            tzinfo=JST,
        ),
    )
    waiting = monitor.poll(
        codes=("7203",),
        observed_at=datetime(
            2026,
            7,
            17,
            9,
            0,
            30,
            tzinfo=JST,
        ),
    )
    resumed = monitor.poll(
        codes=("7203",),
        observed_at=datetime(
            2026,
            7,
            17,
            9,
            1,
            tzinfo=JST,
        ),
    )

    assert first.decision is RealtimePollDecision.NO_NEW_BAR
    assert waiting.decision is RealtimePollDecision.NO_NEW_BAR
    assert waiting.code_count == 0
    assert resumed.decision is RealtimePollDecision.NO_NEW_BAR
    assert call_count == 2


def test_monitor_reraises_non_rate_limit_download_error() -> None:
    """429以外のDownloader例外は従来どおり上位へ返す。"""

    def provider(
        _code: str,
        _target_date: date,
    ) -> list[StockPrice]:
        raise JQuantsDownloadError(
            "server error",
            status_code=500,
        )

    monitor = RealtimeMarketMonitor(
        repository=FakeRepository(),
        bar_provider=provider,
        session_service=TokyoMarketSessionService(
            trading_day_predicate=lambda _date: True
        ),
        data_source="realtime-test",
    )

    with pytest.raises(
        JQuantsDownloadError,
        match="server error",
    ):
        monitor.poll(
            codes=("7203",),
            observed_at=datetime(
                2026,
                7,
                17,
                9,
                0,
                tzinfo=JST,
            ),
        )


@pytest.mark.parametrize(
    ("field_name", "field_value"),
    [
        ("maximum_codes_per_poll", 0),
        ("rate_limit_cooldown_seconds", -1.0),
    ],
)
def test_monitor_rejects_invalid_rate_limit_settings(
    field_name: str,
    field_value: object,
) -> None:
    """不正な取得制御設定を拒否する。"""

    arguments: dict[str, object] = {
        "repository": FakeRepository(),
        "bar_provider": lambda _code, _date: [],
        "data_source": "realtime-test",
    }
    arguments[field_name] = field_value

    with pytest.raises(ValueError):
        RealtimeMarketMonitor(**arguments)
