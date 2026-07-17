"""リアルタイム足からPaper Tradingまでを統括する。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Callable

from app.backtest.backtest_portfolio_update_service import (
    BacktestPortfolioBatchUpdateResult,
    BacktestPortfolioUpdateService,
)
from app.backtest.order_queue_service import (
    BacktestOrderQueueResult,
    BacktestOrderQueueService,
)
from app.backtest.queue_execution_service import (
    BacktestQueueExecutionBatchResult,
    BacktestQueueExecutionItemResult,
    BacktestQueueExecutionService,
)
from app.market.models import StockPrice
from app.market.realtime_signal_engine import (
    RealtimeSignalEngine,
)
from app.market.realtime_signal_models import (
    RealtimeSignalDecision,
    RealtimeSignalProcessResult,
)
from app.trading.order_models import OrderType
from app.trading.signal_models import TradeSignal


class RealtimePaperTradingStatus(StrEnum):
    """リアルタイムPaper Trading処理の終了状態。"""

    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class RealtimePaperTradingResult:
    """リアルタイムPaper Tradingの1サイクル結果。"""

    status: RealtimePaperTradingStatus
    signal_result: RealtimeSignalProcessResult | None
    queue_results: tuple[BacktestOrderQueueResult, ...]
    execution_result: BacktestQueueExecutionBatchResult | None
    portfolio_result: BacktestPortfolioBatchUpdateResult | None
    error_message: str | None = None

    def __post_init__(self) -> None:
        """状態と保持データの整合性を検証する。"""

        if self.status is RealtimePaperTradingStatus.COMPLETED:
            if self.signal_result is None:
                raise ValueError(
                    "完了結果にはシグナル処理結果が必要です。"
                )

            if self.execution_result is None:
                raise ValueError(
                    "完了結果には注文執行結果が必要です。"
                )

            if self.portfolio_result is None:
                raise ValueError(
                    "完了結果にはポートフォリオ結果が必要です。"
                )

            if self.error_message is not None:
                raise ValueError(
                    "完了結果にはエラーメッセージを"
                    "設定できません。"
                )

        if self.status is RealtimePaperTradingStatus.FAILED:
            if not (self.error_message or "").strip():
                raise ValueError(
                    "失敗結果にはエラーメッセージが必要です。"
                )

    @property
    def signal_count(self) -> int:
        """生成シグナル件数を返す。"""

        if self.signal_result is None:
            return 0

        return self.signal_result.signal_count

    @property
    def queued_count(self) -> int:
        """新規キュー登録件数を返す。"""

        return sum(
            result.was_enqueued
            for result in self.queue_results
        )

    @property
    def execution_count(self) -> int:
        """保存済み約定件数を返す。"""

        if self.execution_result is None:
            return 0

        return self.execution_result.saved_execution_count

    @property
    def portfolio_update_count(self) -> int:
        """ポートフォリオ反映件数を返す。"""

        if self.portfolio_result is None:
            return 0

        return self.portfolio_result.applied_count

    @property
    def is_completed(self) -> bool:
        """正常完了したか返す。"""

        return self.status is RealtimePaperTradingStatus.COMPLETED

    @property
    def is_failed(self) -> bool:
        """失敗したか返す。"""

        return self.status is RealtimePaperTradingStatus.FAILED


class RealtimePaperTradingService:
    """足更新・シグナル・注文・約定・資産更新を順番に実行する。"""

    def __init__(
        self,
        *,
        signal_engine: RealtimeSignalEngine,
        order_queue_service: BacktestOrderQueueService,
        queue_execution_service: BacktestQueueExecutionService,
        portfolio_update_service: BacktestPortfolioUpdateService,
        market_price_updater: Callable[[str, float], object],
        clock_updater: Callable[[datetime], None] | None = None,
    ) -> None:
        """Paper Tradingパイプラインの依存関係を設定する。"""

        self.signal_engine = signal_engine
        self.order_queue_service = order_queue_service
        self.queue_execution_service = queue_execution_service
        self.portfolio_update_service = portfolio_update_service
        self.market_price_updater = market_price_updater
        self.clock_updater = clock_updater

    def process(
        self,
        prices: tuple[StockPrice, ...],
        *,
        order_type: OrderType = OrderType.MARKET,
        equity_curve_limit: int = 10_000,
        continue_on_error: bool = False,
    ) -> RealtimePaperTradingResult:
        """新しい足を時系列順にPaper Tradingへ流す。"""

        if equity_curve_limit <= 0:
            raise ValueError(
                "取得件数は0より大きい必要があります。"
            )

        try:
            ordered_prices = tuple(
                sorted(
                    prices,
                    key=lambda price: (
                        self._normalize_datetime(price.datetime),
                        price.code,
                    ),
                )
            )
            signal_results: list[
                RealtimeSignalProcessResult
            ] = []
            queue_results: list[
                BacktestOrderQueueResult
            ] = []
            execution_items: list[
                BacktestQueueExecutionItemResult
            ] = []
            portfolio_items = []

            for price in ordered_prices:
                observed_at = self._normalize_datetime(
                    price.datetime
                )

                if self.clock_updater is not None:
                    self.clock_updater(observed_at)

                self.market_price_updater(
                    price.code,
                    float(price.close),
                )

                single_signal_result = (
                    self.signal_engine.process((price,))
                )
                signal_results.append(
                    single_signal_result
                )

                for signal in single_signal_result.signals:
                    queue_result = (
                        self.order_queue_service.enqueue_signal(
                            signal,
                            order_type=order_type,
                            continue_on_error=continue_on_error,
                        )
                    )
                    queue_results.append(queue_result)

                    if queue_result.is_failed:
                        if continue_on_error:
                            continue

                        raise RuntimeError(
                            queue_result.message
                            or "注文キュー登録に失敗しました。"
                        )

                    execution_result = (
                        self.queue_execution_service.execute_all(
                            continue_on_error=continue_on_error,
                        )
                    )
                    execution_items.extend(
                        execution_result.items
                    )

                    if (
                        execution_result.failed_count > 0
                        and not continue_on_error
                    ):
                        failed = next(
                            item
                            for item in execution_result.items
                            if item.is_failed
                        )
                        raise RuntimeError(
                            failed.message
                            or "注文執行に失敗しました。"
                        )

                    records = tuple(
                        item.execution_record
                        for item in execution_result.items
                        if item.execution_record is not None
                    )
                    portfolio_result = (
                        self.portfolio_update_service
                        .apply_executions(
                            records,
                            equity_curve_limit=(
                                equity_curve_limit
                            ),
                        )
                    )
                    portfolio_items.extend(
                        portfolio_result.items
                    )

            combined_signal_result = (
                self._combine_signal_results(
                    signal_results
                )
            )

            return RealtimePaperTradingResult(
                status=RealtimePaperTradingStatus.COMPLETED,
                signal_result=combined_signal_result,
                queue_results=tuple(queue_results),
                execution_result=(
                    BacktestQueueExecutionBatchResult(
                        items=tuple(execution_items)
                    )
                ),
                portfolio_result=(
                    BacktestPortfolioBatchUpdateResult(
                        items=tuple(portfolio_items)
                    )
                ),
                error_message=None,
            )

        except Exception as error:
            if not continue_on_error:
                raise

            return RealtimePaperTradingResult(
                status=RealtimePaperTradingStatus.FAILED,
                signal_result=None,
                queue_results=(),
                execution_result=None,
                portfolio_result=None,
                error_message=str(error),
            )

    @staticmethod
    def _combine_signal_results(
        results: list[RealtimeSignalProcessResult],
    ) -> RealtimeSignalProcessResult:
        """足単位のシグナル結果を1サイクル分へ統合する。"""

        if not results:
            return RealtimeSignalProcessResult(
                decision=RealtimeSignalDecision.NO_NEW_BAR,
                input_bar_count=0,
                processed_bar_count=0,
                skipped_duplicate_count=0,
                signal_count=0,
                signals=(),
            )

        signals: tuple[TradeSignal, ...] = tuple(
            signal
            for result in results
            for signal in result.signals
        )
        processed_count = sum(
            result.processed_bar_count
            for result in results
        )
        skipped_count = sum(
            result.skipped_duplicate_count
            for result in results
        )

        if signals:
            decision = (
                RealtimeSignalDecision.SIGNALS_GENERATED
            )
        elif processed_count > 0:
            decision = (
                RealtimeSignalDecision.BAR_PROCESSED
            )
        else:
            decision = RealtimeSignalDecision.NO_NEW_BAR

        return RealtimeSignalProcessResult(
            decision=decision,
            input_bar_count=sum(
                result.input_bar_count
                for result in results
            ),
            processed_bar_count=processed_count,
            skipped_duplicate_count=skipped_count,
            signal_count=len(signals),
            signals=signals,
        )

    @staticmethod
    def _normalize_datetime(
        value: datetime,
    ) -> datetime:
        """時計更新に使用できる日時へ正規化する。"""

        if value.tzinfo is None:
            from zoneinfo import ZoneInfo

            return value.replace(
                tzinfo=ZoneInfo("Asia/Tokyo")
            )

        return value
