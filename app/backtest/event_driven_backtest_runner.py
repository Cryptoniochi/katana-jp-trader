"""市場Frameごとに売買処理を進めるイベント駆動Runner。"""

from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from app.backtest.backtest_portfolio_update_service import (
    BacktestPortfolioBatchUpdateResult,
    BacktestPortfolioUpdateService,
)
from app.backtest.backtest_session import (
    BacktestSession,
    BacktestSessionResult,
)
from app.backtest.market_replay import MarketReplayFrame
from app.backtest.order_queue_service import (
    BacktestOrderQueueResult,
    BacktestOrderQueueService,
)
from app.backtest.queue_execution_service import (
    BacktestQueueExecutionBatchResult,
    BacktestQueueExecutionItemResult,
    BacktestQueueExecutionService,
)
from app.trading.equity_curve_models import EquityCurveReport
from app.trading.order_models import OrderType


@dataclass(frozen=True, slots=True)
class EventDrivenBacktestRunResult:
    """イベント駆動バックテストの実行結果。"""

    session_result: BacktestSessionResult
    queue_results: tuple[BacktestOrderQueueResult, ...]
    execution_result: BacktestQueueExecutionBatchResult
    portfolio_result: BacktestPortfolioBatchUpdateResult

    @property
    def frame_count(self) -> int:
        return self.session_result.frame_count

    @property
    def signal_count(self) -> int:
        return self.session_result.signal_count

    @property
    def queued_count(self) -> int:
        return sum(item.was_enqueued for item in self.queue_results)

    @property
    def execution_count(self) -> int:
        return self.execution_result.saved_execution_count

    @property
    def portfolio_update_count(self) -> int:
        return self.portfolio_result.applied_count

    @property
    def equity_curve_report(self) -> EquityCurveReport | None:
        return self.portfolio_result.latest_equity_curve


class EventDrivenBacktestRunner:
    """Frameごとに価格・注文・約定・資産状態を更新する。"""

    def __init__(
        self,
        *,
        session: BacktestSession,
        order_queue_service: BacktestOrderQueueService,
        queue_execution_service: BacktestQueueExecutionService,
        portfolio_update_service: BacktestPortfolioUpdateService,
        market_price_updater: Callable[[str, float], object],
        clock_updater: Callable[[datetime], None],
    ) -> None:
        self.session = session
        self.order_queue_service = order_queue_service
        self.queue_execution_service = queue_execution_service
        self.portfolio_update_service = portfolio_update_service
        self.market_price_updater = market_price_updater
        self.clock_updater = clock_updater

    def run(
        self,
        *,
        order_type: OrderType = OrderType.MARKET,
        equity_curve_limit: int = 10_000,
        continue_on_error: bool = False,
    ) -> EventDrivenBacktestRunResult:
        """戦略結果をFrame順に売買パイプラインへ流す。"""

        if equity_curve_limit <= 0:
            raise ValueError(
                "取得件数は0より大きい必要があります。"
            )

        session_result = self.session.run(
            continue_on_error=False
        )
        strategy_result = session_result.strategy_result

        if strategy_result is None:
            raise RuntimeError(
                "セッション結果に戦略実行結果がありません。"
            )

        queue_results: list[BacktestOrderQueueResult] = []
        execution_items: list[
            BacktestQueueExecutionItemResult
        ] = []
        portfolio_items = []

        for frame_result in strategy_result.frame_results:
            frame = frame_result.frame
            self._update_frame_context(frame)

            for signal in frame_result.signals:
                self.clock_updater(signal.generated_at)
                self.market_price_updater(
                    signal.code,
                    signal.signal_price,
                )

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
                    self.portfolio_update_service.apply_executions(
                        records,
                        equity_curve_limit=equity_curve_limit,
                    )
                )
                portfolio_items.extend(
                    portfolio_result.items
                )

        return EventDrivenBacktestRunResult(
            session_result=session_result,
            queue_results=tuple(queue_results),
            execution_result=BacktestQueueExecutionBatchResult(
                items=tuple(execution_items)
            ),
            portfolio_result=BacktestPortfolioBatchUpdateResult(
                items=tuple(portfolio_items)
            ),
        )

    def _update_frame_context(
        self,
        frame: MarketReplayFrame,
    ) -> None:
        """現在Frameの時計と市場価格を反映する。"""

        self.clock_updater(frame.replayed_at)
        self.market_price_updater(
            frame.code,
            frame.current_bar.close_price,
        )
