"""リアルタイム5分足を売買戦略へ適用する。"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable
from datetime import datetime
from typing import Protocol
from zoneinfo import ZoneInfo

from app.backtest.historical_models import (
    HistoricalBar,
    MarketTimeframe,
)
from app.backtest.high_breakout_strategy import (
    HighBreakoutStrategy,
    HighBreakoutStrategySettings,
)
from app.backtest.market_replay import MarketReplayFrame
from app.backtest.orb_signal_strategy import (
    OrbSignalDiagnosticSnapshot,
    OrbSignalStrategy,
    OrbSignalStrategySettings,
)
from app.backtest.pullback_breakout_strategy import (
    PullbackBreakoutSettings,
    PullbackBreakoutStrategy,
)
from app.market.models import StockPrice
from app.market.realtime_signal_models import (
    RealtimeSignalDecision,
    RealtimeSignalProcessResult,
)
from app.market.strategy_registry import StrategyRegistry
from app.market.symbol_strategy_router import (
    StrategyRouteDecision,
    SymbolStrategyRouter,
)
from app.trading.signal_models import TradeSignal


JST = ZoneInfo("Asia/Tokyo")
SUPPORTED_STRATEGY_NAMES = frozenset(
    {
        "orb",
        "pullback",
        "high-breakout",
    }
)


class RealtimeStrategy(Protocol):
    """リアルタイム戦略が満たすインターフェース。"""

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
        """現在までの診断集計を返す。"""


StrategyFactory = Callable[[str], RealtimeStrategy]


class RealtimeSignalEngine:
    """新しい5分足だけを銘柄別戦略へ適用する。"""

    def __init__(
        self,
        *,
        strategy_factory: StrategyFactory | None = None,
        strategy_registry: StrategyRegistry | None = None,
        enabled_strategy_names: tuple[str, ...] = ("orb",),
        high_breakout_candidate_provider=None,
        symbol_strategy_router: SymbolStrategyRouter | None = None,
    ) -> None:
        """戦略Factory、Registry、銘柄別Routerを設定する。"""

        if (
            strategy_factory is not None
            and strategy_registry is not None
        ):
            raise ValueError(
                "strategy_factoryとstrategy_registryは"
                "同時に指定できません。"
            )

        normalized_enabled = tuple(
            dict.fromkeys(
                name.strip().lower()
                for name in enabled_strategy_names
                if name.strip()
            )
        )

        if not normalized_enabled:
            raise ValueError(
                "有効戦略を1件以上指定してください。"
            )

        unknown = tuple(
            name
            for name in normalized_enabled
            if name not in SUPPORTED_STRATEGY_NAMES
        )

        if unknown:
            raise ValueError(
                "未対応の戦略が指定されています。 "
                f"strategies={','.join(unknown)}"
            )

        if (
            symbol_strategy_router is not None
            and (
                strategy_factory is not None
                or strategy_registry is not None
            )
        ):
            raise ValueError(
                "銘柄別戦略Routerは標準Strategy Registryと"
                "組み合わせて使用してください。"
            )

        self.enabled_strategy_names = normalized_enabled
        self.symbol_strategy_router = symbol_strategy_router
        self.high_breakout_candidate_provider = (
            high_breakout_candidate_provider
        )

        if strategy_registry is not None:
            self.strategy_factory = strategy_registry.create
            self.strategy_registry = strategy_registry
        elif strategy_factory is not None:
            self.strategy_factory = strategy_factory
            self.strategy_registry = None
        else:
            self.strategy_factory = self._create_strategy_for_code
            self.strategy_registry = None

        self._strategies: dict[str, RealtimeStrategy] = {}
        self._bars_by_code: dict[
            str,
            list[HistoricalBar],
        ] = defaultdict(list)
        self._last_processed_at: dict[
            str,
            datetime,
        ] = {}
        self._route_decisions: dict[
            str,
            StrategyRouteDecision,
        ] = {}

    def update_symbol_strategy_router(
        self,
        symbol_strategy_router: SymbolStrategyRouter | None,
    ) -> tuple[str, ...]:
        """Routerを更新し、実効Routeが変わった銘柄だけ再生成対象にする。"""

        changed_codes: list[str] = []

        for code in tuple(self._strategies):
            previous = self._route_decisions.get(code)
            next_decision = self._resolve_route_with_router(
                code,
                symbol_strategy_router,
            )

            if (
                previous is None
                or previous.strategy_names
                != next_decision.strategy_names
                or previous.routed != next_decision.routed
            ):
                strategy = self._strategies.pop(code, None)
                if strategy is not None:
                    strategy.reset()
                self._route_decisions.pop(code, None)
                changed_codes.append(code)

        self.symbol_strategy_router = symbol_strategy_router
        return tuple(changed_codes)

    def process(
        self,
        prices: Iterable[StockPrice],
    ) -> RealtimeSignalProcessResult:
        """未処理の5分足だけを時系列順に評価する。"""

        materialized = tuple(prices)

        if not materialized:
            return RealtimeSignalProcessResult(
                decision=RealtimeSignalDecision.NO_NEW_BAR,
                input_bar_count=0,
                processed_bar_count=0,
                skipped_duplicate_count=0,
                signal_count=0,
                signals=(),
            )

        ordered = sorted(
            materialized,
            key=lambda price: (
                self._normalize_datetime(price.datetime),
                price.code,
            ),
        )
        processed_count = 0
        skipped_count = 0
        generated_signals: list[TradeSignal] = []

        for price in ordered:
            code = self._normalize_code(price.code)
            opened_at = self._normalize_datetime(
                price.datetime
            )
            last_processed = self._last_processed_at.get(code)

            if (
                last_processed is not None
                and opened_at <= last_processed
            ):
                skipped_count += 1
                continue

            bar = self._to_historical_bar(
                price,
                code=code,
                opened_at=opened_at,
            )
            visible_bars = self._bars_by_code[code]
            visible_bars.append(bar)

            strategy = self._strategies.get(code)

            if strategy is None:
                strategy = self.strategy_factory(code)
                self._strategies[code] = strategy

            frame = MarketReplayFrame(
                current_bar=bar,
                visible_bars=tuple(visible_bars),
                index=len(visible_bars) - 1,
                total_count=len(visible_bars),
            )
            signals = strategy.evaluate(frame)
            generated_signals.extend(signals)
            self._last_processed_at[code] = opened_at
            processed_count += 1

        if processed_count == 0:
            decision = RealtimeSignalDecision.NO_NEW_BAR
        elif generated_signals:
            decision = RealtimeSignalDecision.SIGNALS_GENERATED
        else:
            decision = RealtimeSignalDecision.BAR_PROCESSED

        return RealtimeSignalProcessResult(
            decision=decision,
            input_bar_count=len(materialized),
            processed_bar_count=processed_count,
            skipped_duplicate_count=skipped_count,
            signal_count=len(generated_signals),
            signals=tuple(generated_signals),
        )

    def reset(
        self,
        code: str | None = None,
    ) -> None:
        """全銘柄または指定銘柄の状態を初期化する。"""

        if code is None:
            for strategy in self._strategies.values():
                strategy.reset()

            self._strategies.clear()
            self._bars_by_code.clear()
            self._last_processed_at.clear()
            self._route_decisions.clear()
            return

        normalized_code = self._normalize_code(code)
        strategy = self._strategies.pop(
            normalized_code,
            None,
        )

        if strategy is not None:
            strategy.reset()

        self._bars_by_code.pop(normalized_code, None)
        self._last_processed_at.pop(normalized_code, None)
        self._route_decisions.pop(normalized_code, None)

    def diagnostic_snapshot(
        self,
        code: str | None = None,
    ) -> OrbSignalDiagnosticSnapshot:
        """全銘柄または指定銘柄の戦略診断集計を返す。"""

        if code is not None:
            strategy = self._strategies.get(
                self._normalize_code(code)
            )
            if strategy is None:
                return OrbSignalDiagnosticSnapshot(
                    evaluation_count=0,
                    counts={},
                )
            getter = getattr(
                strategy,
                "diagnostic_snapshot",
                None,
            )
            if getter is None:
                return OrbSignalDiagnosticSnapshot(
                    evaluation_count=0,
                    counts={},
                )
            return getter()

        total_evaluations = 0
        total_counts: dict[str, int] = defaultdict(int)

        for strategy in self._strategies.values():
            getter = getattr(
                strategy,
                "diagnostic_snapshot",
                None,
            )
            if getter is None:
                continue

            snapshot = getter()
            total_evaluations += snapshot.evaluation_count

            for reason, count in snapshot.counts.items():
                total_counts[reason] += count

        return OrbSignalDiagnosticSnapshot(
            evaluation_count=total_evaluations,
            counts=dict(total_counts),
        )

    def last_processed_at(
        self,
        code: str,
    ) -> datetime | None:
        """指定銘柄の最終処理日時を返す。"""

        return self._last_processed_at.get(
            self._normalize_code(code)
        )

    def route_decision(
        self,
        code: str,
    ) -> StrategyRouteDecision | None:
        """指定銘柄へ実際に適用した戦略ルートを返す。"""

        return self._route_decisions.get(
            self._normalize_code(code)
        )

    def active_strategy_names(
        self,
        code: str,
    ) -> tuple[str, ...]:
        """指定銘柄で有効になった戦略名を返す。"""

        decision = self.route_decision(code)

        if decision is not None:
            return decision.strategy_names

        return self.enabled_strategy_names

    def _create_strategy_for_code(
        self,
        code: str,
    ) -> RealtimeStrategy:
        """銘柄ルートに応じたStrategy Registryを作成する。"""

        decision = self._resolve_route(code)
        self._route_decisions[code] = decision

        return self._default_registry(
            decision.strategy_names,
            self.high_breakout_candidate_provider,
        ).create(code)

    def _resolve_route(
        self,
        code: str,
    ) -> StrategyRouteDecision:
        return self._resolve_route_with_router(
            code,
            self.symbol_strategy_router,
        )

    def _resolve_route_with_router(
        self,
        code: str,
        symbol_strategy_router: SymbolStrategyRouter | None,
    ) -> StrategyRouteDecision:
        if symbol_strategy_router is None:
            return StrategyRouteDecision(
                code=code,
                strategy_names=self.enabled_strategy_names,
                routed=False,
                reason=(
                    "Symbol Strategy Router is not configured; "
                    "globally enabled strategies are used."
                ),
            )

        routed = symbol_strategy_router.resolve(code)
        allowed = tuple(
            name
            for name in routed.strategy_names
            if name in self.enabled_strategy_names
        )

        if routed.routed and allowed:
            return StrategyRouteDecision(
                code=code,
                strategy_names=allowed,
                routed=True,
                reason=routed.reason,
            )

        return StrategyRouteDecision(
            code=code,
            strategy_names=self.enabled_strategy_names,
            routed=False,
            reason=(
                routed.reason
                + " Route was not allowed by globally enabled "
                "strategies; global fallback is used."
                if routed.routed
                else routed.reason
            ),
        )

    @staticmethod
    def _default_registry(
        enabled_strategy_names: tuple[str, ...],
        high_breakout_candidate_provider,
    ) -> StrategyRegistry:
        """標準戦略を登録したRegistryを作成する。"""

        return StrategyRegistry(
            factories={
                "orb": (
                    lambda _code: OrbSignalStrategy(
                        settings=OrbSignalStrategySettings()
                    )
                ),
                "pullback": (
                    lambda _code: PullbackBreakoutStrategy(
                        settings=PullbackBreakoutSettings()
                    )
                ),
                "high-breakout": (
                    lambda _code: HighBreakoutStrategy(
                        candidate_provider=(
                            high_breakout_candidate_provider
                            or (lambda _code, _date: None)
                        ),
                        settings=HighBreakoutStrategySettings(),
                    )
                ),
            },
            enabled_strategy_names=enabled_strategy_names,
        )

    @staticmethod
    def _to_historical_bar(
        price: StockPrice,
        *,
        code: str,
        opened_at: datetime,
    ) -> HistoricalBar:
        """StockPriceを5分足モデルへ変換する。"""

        return HistoricalBar(
            code=code,
            timeframe=MarketTimeframe.MINUTE_5,
            opened_at=opened_at,
            open_price=float(price.open),
            high_price=float(price.high),
            low_price=float(price.low),
            close_price=float(price.close),
            volume=float(price.volume),
        )

    @staticmethod
    def _normalize_code(
        code: str,
    ) -> str:
        """銘柄コードを検証する。"""

        normalized = code.strip()

        if not normalized.isdigit():
            raise ValueError(
                "銘柄コードは数字で指定してください。"
            )

        if len(normalized) not in {4, 5}:
            raise ValueError(
                "銘柄コードは4桁または5桁で指定してください。"
            )

        return normalized

    @staticmethod
    def _normalize_datetime(
        value: datetime,
    ) -> datetime:
        """市場日時を日本時間へ正規化する。"""

        if value.tzinfo is None:
            return value.replace(tzinfo=JST)

        return value.astimezone(JST)
