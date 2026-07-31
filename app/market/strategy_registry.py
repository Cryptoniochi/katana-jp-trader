"""リアルタイム売買戦略の登録・合成を管理する。"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import replace
from typing import Protocol

from app.backtest.market_replay import MarketReplayFrame
from app.backtest.orb_signal_strategy import (
    OrbSignalDiagnosticSnapshot,
)
from app.trading.signal_models import (
    SignalAction,
    TradeSignal,
)


class RegisteredRealtimeStrategy(Protocol):
    """Registryへ登録できるリアルタイム戦略。"""

    strategy_name: str

    def evaluate(
        self,
        frame: MarketReplayFrame,
    ) -> tuple[TradeSignal, ...]:
        """現在Frameを評価してシグナルを返す。"""

    def reset(self) -> None:
        """内部状態を初期化する。"""

    def diagnostic_snapshot(
        self,
    ) -> OrbSignalDiagnosticSnapshot:
        """診断集計を返す。"""


StrategyFactory = Callable[[str], RegisteredRealtimeStrategy]


class StrategyRegistry:
    """有効な戦略Factoryを登録順付きで保持する。"""

    def __init__(
        self,
        factories: Mapping[str, StrategyFactory],
        *,
        enabled_strategy_names: tuple[str, ...] | None = None,
    ) -> None:
        """戦略Factoryと有効戦略名を設定する。"""

        normalized_factories: dict[str, StrategyFactory] = {}

        for raw_name, factory in factories.items():
            name = self._normalize_name(raw_name)

            if name in normalized_factories:
                raise ValueError(
                    "戦略名が重複しています。 "
                    f"strategy={name}"
                )

            normalized_factories[name] = factory

        if not normalized_factories:
            raise ValueError(
                "戦略Factoryを1件以上登録してください。"
            )

        if enabled_strategy_names is None:
            enabled = tuple(normalized_factories)
        else:
            enabled = tuple(
                dict.fromkeys(
                    self._normalize_name(name)
                    for name in enabled_strategy_names
                )
            )

        if not enabled:
            raise ValueError(
                "有効戦略を1件以上指定してください。"
            )

        unknown = tuple(
            name
            for name in enabled
            if name not in normalized_factories
        )

        if unknown:
            raise ValueError(
                "未登録の戦略が指定されています。 "
                f"strategies={','.join(unknown)}"
            )

        self._factories = normalized_factories
        self._enabled = enabled

    @property
    def enabled_strategy_names(self) -> tuple[str, ...]:
        """有効戦略名を登録順で返す。"""

        return self._enabled

    def create(
        self,
        code: str,
    ) -> "CompositeRealtimeStrategy":
        """指定銘柄用の複合戦略を作成する。"""

        strategies = tuple(
            self._factories[name](code)
            for name in self._enabled
        )

        actual_names = tuple(
            self._normalize_name(strategy.strategy_name)
            for strategy in strategies
        )

        if len(set(actual_names)) != len(actual_names):
            raise ValueError(
                "生成された戦略のstrategy_nameが"
                "重複しています。"
            )

        return CompositeRealtimeStrategy(
            strategies=strategies
        )

    @staticmethod
    def _normalize_name(name: str) -> str:
        normalized = name.strip().lower()

        if not normalized:
            raise ValueError(
                "戦略名を指定してください。"
            )

        return normalized


class CompositeRealtimeStrategy:
    """複数戦略を評価し、同一足の競合を安全に解決する。"""

    strategy_name = "strategy-registry"

    def __init__(
        self,
        *,
        strategies: tuple[RegisteredRealtimeStrategy, ...],
    ) -> None:
        if not strategies:
            raise ValueError(
                "複合戦略には1件以上の戦略が必要です。"
            )

        self._strategies = strategies
        self._conflict_counts: Counter[str] = Counter()
        self._evaluation_count = 0

    @property
    def strategy_names(self) -> tuple[str, ...]:
        """内包する戦略名を返す。"""

        return tuple(
            strategy.strategy_name
            for strategy in self._strategies
        )

    def evaluate(
        self,
        frame: MarketReplayFrame,
    ) -> tuple[TradeSignal, ...]:
        """全戦略を評価し、重複と逆方向競合を解決する。"""

        self._evaluation_count += 1
        generated = tuple(
            signal
            for strategy in self._strategies
            for signal in strategy.evaluate(frame)
        )

        if len(generated) <= 1:
            return generated

        actions = {
            signal.action
            for signal in generated
        }

        has_entry = bool(
            actions & {
                SignalAction.BUY,
                SignalAction.SELL,
            }
        )
        has_exit = SignalAction.EXIT in actions
        has_opposite_entries = (
            SignalAction.BUY in actions
            and SignalAction.SELL in actions
        )

        if has_opposite_entries or (
            has_exit
            and has_entry
        ):
            self._conflict_counts[
                "signal_conflict_suppressed"
            ] += 1
            return ()

        grouped: dict[
            tuple[str, SignalAction],
            list[TradeSignal],
        ] = {}

        for signal in generated:
            key = (
                signal.code,
                signal.action,
            )
            grouped.setdefault(key, []).append(signal)

        resolved: list[TradeSignal] = []

        for signals in grouped.values():
            primary = signals[0]

            if len(signals) == 1:
                resolved.append(primary)
                continue

            supporting = tuple(
                signal.strategy_name
                for signal in signals
            )
            metadata = dict(primary.metadata)
            metadata["supporting_strategies"] = supporting
            metadata["strategy_consensus_count"] = len(
                supporting
            )

            resolved.append(
                replace(
                    primary,
                    metadata=metadata,
                )
            )
            self._conflict_counts[
                "same_direction_merged"
            ] += len(signals) - 1

        return tuple(resolved)

    def reset(self) -> None:
        """全戦略とRegistry診断を初期化する。"""

        for strategy in self._strategies:
            strategy.reset()

        self._conflict_counts.clear()
        self._evaluation_count = 0

    def diagnostic_snapshot(
        self,
    ) -> OrbSignalDiagnosticSnapshot:
        """戦略別・全体の診断集計を返す。"""

        totals: Counter[str] = Counter(
            self._conflict_counts
        )
        total_evaluations = 0

        for strategy in self._strategies:
            snapshot = strategy.diagnostic_snapshot()
            total_evaluations += snapshot.evaluation_count

            for reason, count in snapshot.counts.items():
                totals[reason] += count
                totals[
                    f"strategy.{strategy.strategy_name}.{reason}"
                ] += count

        totals["registry_frame_evaluations"] = (
            self._evaluation_count
        )

        return OrbSignalDiagnosticSnapshot(
            evaluation_count=total_evaluations,
            counts=dict(totals),
        )
