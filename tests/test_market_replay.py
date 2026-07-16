"""バックテスト履歴モデルと時系列リプレイのテスト。"""

from datetime import datetime, timedelta, timezone

import pytest

from app.backtest.historical_models import (
    HistoricalBar,
    HistoricalBarSeries,
    MarketTimeframe,
)
from app.backtest.market_replay import (
    MarketReplayEngine,
    MarketReplaySettings,
)


BASE_TIME = datetime(
    2026,
    7,
    1,
    0,
    0,
    tzinfo=timezone.utc,
)


def create_bar(
    *,
    minute: int,
    code: str = "7203",
    timeframe: MarketTimeframe = MarketTimeframe.MINUTE_5,
    open_price: float = 2500.0,
    high_price: float = 2520.0,
    low_price: float = 2490.0,
    close_price: float = 2510.0,
    volume: float = 1000.0,
) -> HistoricalBar:
    """標準的なローソク足を作成する。"""

    return HistoricalBar(
        code=code,
        timeframe=timeframe,
        opened_at=BASE_TIME + timedelta(minutes=minute),
        open_price=open_price,
        high_price=high_price,
        low_price=low_price,
        close_price=close_price,
        volume=volume,
    )


def create_series(
    *,
    count: int = 4,
) -> HistoricalBarSeries:
    """5分足系列を作成する。"""

    return HistoricalBarSeries(
        code="7203",
        timeframe=MarketTimeframe.MINUTE_5,
        bars=tuple(
            create_bar(minute=index * 5)
            for index in range(count)
        ),
    )


def test_historical_bar_calculates_properties() -> None:
    """終了日時・代表価格・値幅を計算する。"""

    bar = create_bar(minute=0)

    assert bar.closed_at == BASE_TIME + timedelta(minutes=5)
    assert bar.typical_price == pytest.approx(
        (2520.0 + 2490.0 + 2510.0) / 3.0
    )
    assert bar.price_range == pytest.approx(30.0)


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        ({"code": "ABC"}, "数字"),
        ({"open_price": 0.0}, "始値"),
        ({"high_price": 2480.0}, "高値は安値以上"),
        ({"open_price": 2530.0}, "始値"),
        ({"close_price": 2480.0}, "終値"),
        ({"volume": -1.0}, "出来高"),
    ],
)
def test_historical_bar_rejects_invalid_values(
    arguments: dict[str, object],
    message: str,
) -> None:
    """不正なOHLCVを拒否する。"""

    base_arguments: dict[str, object] = {
        "code": "7203",
        "timeframe": MarketTimeframe.MINUTE_5,
        "opened_at": BASE_TIME,
        "open_price": 2500.0,
        "high_price": 2520.0,
        "low_price": 2490.0,
        "close_price": 2510.0,
        "volume": 1000.0,
    }
    base_arguments.update(arguments)

    with pytest.raises(ValueError, match=message):
        HistoricalBar(**base_arguments)


def test_historical_bar_rejects_naive_datetime() -> None:
    """タイムゾーンなし日時を拒否する。"""

    with pytest.raises(ValueError, match="タイムゾーン"):
        HistoricalBar(
            code="7203",
            timeframe=MarketTimeframe.MINUTE_5,
            opened_at=datetime(2026, 7, 1, 9, 0),
            open_price=2500.0,
            high_price=2520.0,
            low_price=2490.0,
            close_price=2510.0,
            volume=1000.0,
        )


def test_series_exposes_range_and_count() -> None:
    """系列の件数と開始・終了日時を返す。"""

    series = create_series(count=3)

    assert series.bar_count == 3
    assert series.started_at == BASE_TIME
    assert series.ended_at == BASE_TIME + timedelta(minutes=15)


def test_series_rejects_code_mismatch() -> None:
    """異なる銘柄を含む系列を拒否する。"""

    with pytest.raises(ValueError, match="銘柄コード"):
        HistoricalBarSeries(
            code="7203",
            timeframe=MarketTimeframe.MINUTE_5,
            bars=(
                create_bar(minute=0),
                create_bar(minute=5, code="8306"),
            ),
        )


def test_series_rejects_timeframe_mismatch() -> None:
    """異なる時間軸を含む系列を拒否する。"""

    with pytest.raises(ValueError, match="時間軸"):
        HistoricalBarSeries(
            code="7203",
            timeframe=MarketTimeframe.MINUTE_5,
            bars=(
                create_bar(minute=0),
                create_bar(
                    minute=5,
                    timeframe=MarketTimeframe.MINUTE_1,
                ),
            ),
        )


def test_series_rejects_duplicate_or_unsorted_bars() -> None:
    """重複・逆順のローソク足を拒否する。"""

    with pytest.raises(ValueError, match="昇順"):
        HistoricalBarSeries(
            code="7203",
            timeframe=MarketTimeframe.MINUTE_5,
            bars=(
                create_bar(minute=5),
                create_bar(minute=0),
            ),
        )


def test_replay_exposes_only_current_and_past_bars() -> None:
    """各Frameが未来のローソク足を公開しない。"""

    frames = MarketReplayEngine(
        create_series(count=4)
    ).replay()

    assert len(frames) == 4

    for index, frame in enumerate(frames):
        assert len(frame.visible_bars) == index + 1
        assert frame.current_bar == frame.visible_bars[-1]
        assert all(
            bar.opened_at <= frame.current_bar.opened_at
            for bar in frame.visible_bars
        )

    assert frames[0].is_first
    assert not frames[0].is_last
    assert frames[-1].is_last


def test_replay_applies_warmup_without_hiding_history() -> None:
    """ウォームアップ後に開始しつつ過去履歴を公開する。"""

    frames = MarketReplayEngine(
        create_series(count=4),
        settings=MarketReplaySettings(
            warmup_bars=2,
        ),
    ).replay()

    assert len(frames) == 2
    assert frames[0].current_bar.opened_at == (
        BASE_TIME + timedelta(minutes=10)
    )
    assert len(frames[0].visible_bars) == 3


def test_replay_filters_period_inclusively() -> None:
    """開始・終了日時を含む範囲だけを再生する。"""

    frames = MarketReplayEngine(
        create_series(count=5),
        settings=MarketReplaySettings(
            start_at=BASE_TIME + timedelta(minutes=5),
            end_at=BASE_TIME + timedelta(minutes=15),
        ),
    ).replay()

    assert [
        frame.current_bar.opened_at
        for frame in frames
    ] == [
        BASE_TIME + timedelta(minutes=5),
        BASE_TIME + timedelta(minutes=10),
        BASE_TIME + timedelta(minutes=15),
    ]


def test_replay_returns_empty_when_no_bar_matches() -> None:
    """条件に一致する履歴がなければ空を返す。"""

    frames = MarketReplayEngine(
        create_series(count=2),
        settings=MarketReplaySettings(
            start_at=BASE_TIME + timedelta(days=1),
        ),
    ).replay()

    assert frames == ()


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        ({"warmup_bars": -1}, "ウォームアップ"),
        (
            {
                "start_at": BASE_TIME + timedelta(minutes=10),
                "end_at": BASE_TIME,
            },
            "終了日時",
        ),
    ],
)
def test_replay_settings_reject_invalid_values(
    arguments: dict[str, object],
    message: str,
) -> None:
    """不正な再生条件を拒否する。"""

    with pytest.raises(ValueError, match=message):
        MarketReplaySettings(**arguments)
