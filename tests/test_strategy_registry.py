"""StrategyRegistryのテスト。"""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.backtest.historical_models import (
    HistoricalBar,
    MarketTimeframe,
)
from app.backtest.market_replay import MarketReplayFrame
from app.backtest.orb_signal_strategy import (
    OrbSignalDiagnosticSnapshot,
)
from app.market.strategy_registry import StrategyRegistry
from app.trading.signal_models import (
    SignalAction,
    TradeSignal,
)


JST = ZoneInfo("Asia/Tokyo")


def frame() -> MarketReplayFrame:
    bar = HistoricalBar(
        code="7203",
        timeframe=MarketTimeframe.MINUTE_5,
        opened_at=datetime(
            2026,
            8,
            3,
            9,
            20,
            tzinfo=JST,
        ),
        open_price=1000.0,
        high_price=1010.0,
        low_price=990.0,
        close_price=1005.0,
        volume=1000.0,
    )
    return MarketReplayFrame(
        current_bar=bar,
        visible_bars=(bar,),
        index=0,
        total_count=1,
    )


class FakeStrategy:
    def __init__(
        self,
        name: str,
        action: SignalAction | None,
    ) -> None:
        self.strategy_name = name
        self.action = action
        self.reset_count = 0

    def evaluate(self, current_frame):
        if self.action is None:
            return ()

        return (
            TradeSignal(
                signal_id=(
                    f"{self.strategy_name}-"
                    f"{self.action.value}-1"
                ),
                code=current_frame.code,
                strategy_name=self.strategy_name,
                action=self.action,
                generated_at=current_frame.replayed_at,
                signal_price=(
                    current_frame.current_bar.close_price
                ),
                quantity=100,
                reason="test",
            ),
        )

    def reset(self):
        self.reset_count += 1

    def diagnostic_snapshot(self):
        return OrbSignalDiagnosticSnapshot(
            evaluation_count=1,
            counts={"buy_signal": 1},
        )


def test_registry_creates_enabled_strategies_in_order() -> None:
    registry = StrategyRegistry(
        factories={
            "orb": lambda _code: FakeStrategy(
                "orb",
                SignalAction.BUY,
            ),
            "pullback": lambda _code: FakeStrategy(
                "pullback",
                None,
            ),
        },
        enabled_strategy_names=(
            "pullback",
            "orb",
        ),
    )

    composite = registry.create("7203")

    assert composite.strategy_names == (
        "pullback",
        "orb",
    )


def test_same_direction_signals_are_merged() -> None:
    registry = StrategyRegistry(
        factories={
            "first": lambda _code: FakeStrategy(
                "first",
                SignalAction.BUY,
            ),
            "second": lambda _code: FakeStrategy(
                "second",
                SignalAction.BUY,
            ),
        }
    )

    signals = registry.create("7203").evaluate(frame())

    assert len(signals) == 1
    assert signals[0].strategy_name == "first"
    assert signals[0].metadata[
        "supporting_strategies"
    ] == ("first", "second")
    assert signals[0].metadata[
        "strategy_consensus_count"
    ] == 2


def test_opposite_signals_are_suppressed() -> None:
    composite = StrategyRegistry(
        factories={
            "buyer": lambda _code: FakeStrategy(
                "buyer",
                SignalAction.BUY,
            ),
            "seller": lambda _code: FakeStrategy(
                "seller",
                SignalAction.SELL,
            ),
        }
    ).create("7203")

    assert composite.evaluate(frame()) == ()
    assert (
        composite.diagnostic_snapshot().counts[
            "signal_conflict_suppressed"
        ]
        == 1
    )


def test_exit_and_entry_conflict_is_suppressed() -> None:
    composite = StrategyRegistry(
        factories={
            "exit": lambda _code: FakeStrategy(
                "exit",
                SignalAction.EXIT,
            ),
            "entry": lambda _code: FakeStrategy(
                "entry",
                SignalAction.BUY,
            ),
        }
    ).create("7203")

    assert composite.evaluate(frame()) == ()


def test_registry_rejects_unknown_enabled_strategy() -> None:
    with pytest.raises(ValueError, match="未登録"):
        StrategyRegistry(
            factories={
                "orb": lambda _code: FakeStrategy(
                    "orb",
                    None,
                ),
            },
            enabled_strategy_names=("unknown",),
        )


def test_composite_reset_resets_all_strategies() -> None:
    first = FakeStrategy("first", None)
    second = FakeStrategy("second", None)
    composite = StrategyRegistry(
        factories={
            "first": lambda _code: first,
            "second": lambda _code: second,
        }
    ).create("7203")

    composite.reset()

    assert first.reset_count == 1
    assert second.reset_count == 1
