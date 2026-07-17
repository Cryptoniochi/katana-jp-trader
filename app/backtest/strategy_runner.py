"""時系列リプレイ上で売買戦略を安全に実行する。"""

from dataclasses import dataclass
from typing import Protocol

from app.backtest.market_replay import (
    MarketReplayEngine,
    MarketReplayFrame,
)
from app.trading.signal_models import TradeSignal


class BacktestStrategy(Protocol):
    """バックテスト戦略の共通インターフェース。"""

    @property
    def strategy_name(self) -> str:
        """戦略名を返す。"""

    def evaluate(
        self,
        frame: MarketReplayFrame,
    ) -> tuple[TradeSignal, ...]:
        """現在時点までの履歴からシグナルを生成する。"""


class BacktestStrategyValidationError(RuntimeError):
    """戦略が不正なシグナルを生成したことを表す。"""


@dataclass(frozen=True, slots=True)
class StrategyFrameResult:
    """1つのMarketReplayFrameに対する戦略実行結果。"""

    frame: MarketReplayFrame
    signals: tuple[
        TradeSignal,
        ...
    ]

    @property
    def signal_count(self) -> int:
        """生成シグナル件数を返す。"""

        return len(self.signals)

    @property
    def has_signal(self) -> bool:
        """シグナルが1件以上あるか返す。"""

        return bool(self.signals)


@dataclass(frozen=True, slots=True)
class StrategyRunResult:
    """全リプレイ期間の戦略実行結果。"""

    strategy_name: str
    frame_results: tuple[
        StrategyFrameResult,
        ...
    ]
    signals: tuple[
        TradeSignal,
        ...
    ]

    def __post_init__(self) -> None:
        """戦略名を検証して正規化する。"""

        normalized_strategy_name = self.strategy_name.strip()

        if not normalized_strategy_name:
            raise ValueError(
                "戦略名を指定してください。"
            )

        object.__setattr__(
            self,
            "strategy_name",
            normalized_strategy_name,
        )

    @property
    def frame_count(self) -> int:
        """実行したFrame件数を返す。"""

        return len(self.frame_results)

    @property
    def signal_count(self) -> int:
        """生成した全シグナル件数を返す。"""

        return len(self.signals)

    @property
    def signaled_frame_count(self) -> int:
        """シグナルが生成されたFrame件数を返す。"""

        return sum(
            1
            for result in self.frame_results
            if result.has_signal
        )


class BacktestStrategyRunner:
    """MarketReplayEngine上で戦略を時系列実行する。"""

    def __init__(
        self,
        *,
        replay_engine: MarketReplayEngine,
        strategy: BacktestStrategy,
    ) -> None:
        """リプレイエンジンと戦略を設定する。"""

        normalized_strategy_name = (
            strategy.strategy_name.strip()
        )

        if not normalized_strategy_name:
            raise ValueError(
                "戦略名を指定してください。"
            )

        self.replay_engine = replay_engine
        self.strategy = strategy
        self.strategy_name = normalized_strategy_name

    def run(self) -> StrategyRunResult:
        """全Frameで戦略を実行してシグナルを収集する。"""

        frame_results: list[
            StrategyFrameResult
        ] = []
        collected_signals: list[
            TradeSignal
        ] = []
        seen_signal_ids: set[str] = set()

        for frame in self.replay_engine.frames():
            signals = tuple(
                self.strategy.evaluate(frame)
            )

            for signal in signals:
                self._validate_signal(
                    signal=signal,
                    frame=frame,
                    seen_signal_ids=seen_signal_ids,
                )
                seen_signal_ids.add(signal.signal_id)
                collected_signals.append(signal)

            frame_results.append(
                StrategyFrameResult(
                    frame=frame,
                    signals=signals,
                )
            )

        return StrategyRunResult(
            strategy_name=self.strategy_name,
            frame_results=tuple(frame_results),
            signals=tuple(collected_signals),
        )

    def _validate_signal(
        self,
        *,
        signal: TradeSignal,
        frame: MarketReplayFrame,
        seen_signal_ids: set[str],
    ) -> None:
        """戦略が生成したシグナルの整合性を検証する。"""

        if signal.strategy_name != self.strategy_name:
            raise BacktestStrategyValidationError(
                "シグナルの戦略名がRunnerの戦略名と"
                "一致しません。 "
                f"expected={self.strategy_name} "
                f"actual={signal.strategy_name}"
            )

        if signal.code != frame.code:
            raise BacktestStrategyValidationError(
                "シグナルの銘柄コードが現在Frameと"
                "一致しません。 "
                f"expected={frame.code} "
                f"actual={signal.code}"
            )

        if signal.generated_at > frame.replayed_at:
            raise BacktestStrategyValidationError(
                "シグナル生成日時が現在のリプレイ時刻より"
                "未来です。 "
                f"generated_at={signal.generated_at.isoformat()} "
                f"replayed_at={frame.replayed_at.isoformat()}"
            )

        if signal.signal_id in seen_signal_ids:
            raise BacktestStrategyValidationError(
                "同じシグナルIDが複数回生成されました。 "
                f"signal_id={signal.signal_id}"
            )
