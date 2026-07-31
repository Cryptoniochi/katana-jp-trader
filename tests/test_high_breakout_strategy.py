"""HighBreakoutStrategyのテスト。"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.backtest.high_breakout_strategy import HighBreakoutStrategy
from app.backtest.historical_models import (
    HistoricalBar,
    HistoricalBarSeries,
    MarketTimeframe,
)
from app.backtest.market_replay import MarketReplayEngine
from app.backtest.strategy_runner import BacktestStrategyRunner
from app.strategy.high_breakout_models import (
    HighBreakoutCandidate,
    HighBreakoutType,
)
from app.trading.signal_models import SignalAction


JST = ZoneInfo("Asia/Tokyo")


def candidate_provider(code, trading_date):
    return HighBreakoutCandidate(
        code=code,
        trading_date=trading_date,
        breakout_types=(HighBreakoutType.DAY_20,),
        close_price=1000.0,
        previous_20_day_high=995.0,
        previous_60_day_high=None,
        previous_year_high=None,
        volume_ratio=2.0,
        turnover=500_000_000.0,
        atr=20.0,
        atr_rate=0.02,
        score=80.0,
    )


def bar(minute, high, low, close, volume=1000):
    return HistoricalBar(
        code="7203",
        timeframe=MarketTimeframe.MINUTE_5,
        opened_at=datetime(
            2026, 8, 3, 9, minute, tzinfo=JST
        ),
        open_price=close,
        high_price=high,
        low_price=low,
        close_price=close,
        volume=volume,
    )


def run(provider=candidate_provider):
    bars = (
        bar(10, 1000, 995, 998),
        bar(15, 1002, 997, 1000),
        bar(20, 1003, 998, 1001),
        bar(25, 1004, 999, 1002),
        bar(30, 1010, 1001, 1008, 1500),
    )
    strategy = HighBreakoutStrategy(
        candidate_provider=provider
    )
    result = BacktestStrategyRunner(
        replay_engine=MarketReplayEngine(
            HistoricalBarSeries(
                code="7203",
                timeframe=MarketTimeframe.MINUTE_5,
                bars=bars,
            )
        ),
        strategy=strategy,
    ).run()
    return strategy, result


def test_high_breakout_emits_buy() -> None:
    _strategy, result = run()

    assert result.signal_count == 1
    assert result.signals[0].action is SignalAction.BUY
    assert result.signals[0].strategy_name == "high-breakout-v1"


def test_high_breakout_requires_candidate() -> None:
    strategy, result = run(
        provider=lambda _code, _date: None
    )

    assert result.signal_count == 0
    assert strategy.diagnostic_snapshot().counts[
        "no_candidate"
    ] == 5
