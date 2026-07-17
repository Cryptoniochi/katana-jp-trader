"""RealtimeSignalEngineのテスト。"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from app.market.models import StockPrice
from app.market.realtime_signal_engine import (
    RealtimeSignalEngine,
)
from app.market.realtime_signal_models import (
    RealtimeSignalDecision,
)
from app.trading.signal_models import SignalAction


JST = ZoneInfo("Asia/Tokyo")


def price(
    minute: int,
    *,
    high: float,
    low: float,
    close: float,
    code: str = "7203",
) -> StockPrice:
    """ORB評価用5分足を作成する。"""

    return StockPrice(
        code=code,
        datetime=datetime(
            2026,
            7,
            17,
            9,
            minute,
            tzinfo=JST,
        ),
        open=1000.0,
        high=high,
        low=low,
        close=close,
        volume=1000,
    )


def opening_and_breakout_prices(
    code: str = "7203",
) -> list[StockPrice]:
    """BUYシグナルが発生する系列を返す。"""

    return [
        price(0, high=1000.0, low=990.0, close=995.0, code=code),
        price(5, high=1000.0, low=990.0, close=998.0, code=code),
        price(10, high=1000.0, low=995.0, close=999.0, code=code),
        price(15, high=1000.0, low=995.0, close=999.0, code=code),
        price(20, high=1010.0, low=999.0, close=1005.0, code=code),
    ]


def test_engine_generates_orb_buy_signal() -> None:
    """オープニングレンジ突破でBUYを生成する。"""

    result = RealtimeSignalEngine().process(
        opening_and_breakout_prices()
    )

    assert result.decision is (
        RealtimeSignalDecision.SIGNALS_GENERATED
    )
    assert result.processed_bar_count == 5
    assert result.signal_count == 1
    assert result.signals[0].action is SignalAction.BUY
    assert result.signals[0].code == "7203"


def test_engine_skips_duplicate_bars() -> None:
    """同じ開始日時の足を再処理しない。"""

    engine = RealtimeSignalEngine()
    first = engine.process(
        opening_and_breakout_prices()
    )
    second = engine.process(
        opening_and_breakout_prices()
    )

    assert first.signal_count == 1
    assert second.decision is RealtimeSignalDecision.NO_NEW_BAR
    assert second.processed_bar_count == 0
    assert second.skipped_duplicate_count == 5
    assert second.signal_count == 0


def test_engine_processes_only_incremental_bars() -> None:
    """2回目は新しく追加された足だけ処理する。"""

    engine = RealtimeSignalEngine()
    bars = opening_and_breakout_prices()

    first = engine.process(bars[:4])
    second = engine.process(bars)

    assert first.decision is RealtimeSignalDecision.BAR_PROCESSED
    assert first.signal_count == 0
    assert second.processed_bar_count == 1
    assert second.skipped_duplicate_count == 4
    assert second.signal_count == 1


def test_engine_keeps_state_separately_by_code() -> None:
    """戦略状態と最終処理日時を銘柄別に保持する。"""

    engine = RealtimeSignalEngine()
    result = engine.process(
        opening_and_breakout_prices("7203")
        + opening_and_breakout_prices("6758")
    )

    assert result.signal_count == 2
    assert {
        signal.code
        for signal in result.signals
    } == {"7203", "6758"}
    assert engine.last_processed_at("7203") is not None
    assert engine.last_processed_at("6758") is not None


def test_engine_generates_take_profit_exit() -> None:
    """BUY後の利確条件でEXITを生成する。"""

    from app.backtest.orb_signal_strategy import (
        OrbSignalStrategy,
        OrbSignalStrategySettings,
    )

    engine = RealtimeSignalEngine(
        strategy_factory=lambda _code: OrbSignalStrategy(
            settings=OrbSignalStrategySettings(
                take_profit_rate=0.01,
            )
        )
    )
    entry = opening_and_breakout_prices()
    exit_bar = price(
        25,
        high=1020.0,
        low=1000.0,
        close=1015.0,
    )

    result = engine.process(entry + [exit_bar])

    assert result.signal_count == 2
    assert [
        signal.action
        for signal in result.signals
    ] == [SignalAction.BUY, SignalAction.EXIT]


def test_engine_returns_empty_result_for_no_input() -> None:
    """入力なしでは安全な空結果を返す。"""

    result = RealtimeSignalEngine().process(())

    assert result.decision is RealtimeSignalDecision.NO_NEW_BAR
    assert result.input_bar_count == 0
    assert result.processed_bar_count == 0
    assert result.signal_count == 0


def test_engine_sorts_out_of_order_bars() -> None:
    """順不同入力を開始日時順に処理する。"""

    engine = RealtimeSignalEngine()
    bars = opening_and_breakout_prices()
    result = engine.process(tuple(reversed(bars)))

    assert result.processed_bar_count == 5
    assert result.signal_count == 1
    assert engine.last_processed_at("7203") == (
        bars[-1].datetime
    )


def test_engine_reset_one_code_only() -> None:
    """指定銘柄だけ状態を初期化できる。"""

    engine = RealtimeSignalEngine()
    engine.process(
        opening_and_breakout_prices("7203")
        + opening_and_breakout_prices("6758")
    )

    engine.reset("7203")

    assert engine.last_processed_at("7203") is None
    assert engine.last_processed_at("6758") is not None

    result = engine.process(
        opening_and_breakout_prices("7203")
    )
    assert result.signal_count == 1


def test_engine_reset_all_codes() -> None:
    """全銘柄状態を初期化できる。"""

    engine = RealtimeSignalEngine()
    engine.process(
        opening_and_breakout_prices()
    )

    engine.reset()

    assert engine.last_processed_at("7203") is None

    result = engine.process(
        opening_and_breakout_prices()
    )
    assert result.signal_count == 1


def test_engine_accepts_naive_market_datetime_as_jst() -> None:
    """タイムゾーンなし市場時刻をJSTとして扱う。"""

    bar = StockPrice(
        code="7203",
        datetime=datetime(2026, 7, 17, 9, 0),
        open=1000.0,
        high=1010.0,
        low=990.0,
        close=1005.0,
        volume=1000,
    )

    engine = RealtimeSignalEngine()
    result = engine.process((bar,))

    assert result.processed_bar_count == 1
    assert engine.last_processed_at("7203").tzinfo == JST
