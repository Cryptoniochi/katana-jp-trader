"""バックテストの全処理を1回の実行として統括する。"""

from dataclasses import dataclass
from enum import StrEnum

from app.backtest.backtest_portfolio_update_service import (
    BacktestPortfolioBatchUpdateResult,
    BacktestPortfolioUpdateService,
)
from app.backtest.backtest_session import (
    BacktestSession,
    BacktestSessionResult,
)
from app.backtest.order_queue_service import (
    BacktestOrderQueueResult,
    BacktestOrderQueueService,
)
from app.backtest.queue_execution_service import (
    BacktestQueueExecutionBatchResult,
    BacktestQueueExecutionService,
)
from app.trading.equity_curve_models import EquityCurveReport
from app.trading.order_models import OrderType


class BacktestRunStatus(StrEnum):
    """バックテスト全体の終了状態。"""

    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class BacktestRunResult:
    """バックテスト全体の実行結果。"""

    status: BacktestRunStatus
    session_result: BacktestSessionResult | None
    queue_results: tuple[
        BacktestOrderQueueResult,
        ...
    ]
    execution_result: BacktestQueueExecutionBatchResult | None
    portfolio_result: BacktestPortfolioBatchUpdateResult | None
    error_message: str | None

    def __post_init__(self) -> None:
        """結果の整合性を検証する。"""

        if (
            self.status is BacktestRunStatus.COMPLETED
            and self.session_result is None
        ):
            raise ValueError(
                "完了結果にはセッション結果が必要です。"
            )

        if (
            self.status is BacktestRunStatus.FAILED
            and not (self.error_message or "").strip()
        ):
            raise ValueError(
                "失敗結果にはエラーメッセージが必要です。"
            )

    @property
    def is_completed(self) -> bool:
        """正常完了したか返す。"""

        return self.status is BacktestRunStatus.COMPLETED

    @property
    def is_failed(self) -> bool:
        """失敗したか返す。"""

        return self.status is BacktestRunStatus.FAILED

    @property
    def frame_count(self) -> int:
        """処理した市場Frame件数を返す。"""

        if self.session_result is None:
            return 0

        return self.session_result.frame_count

    @property
    def signal_count(self) -> int:
        """戦略が生成したシグナル件数を返す。"""

        if self.session_result is None:
            return 0

        return self.session_result.signal_count

    @property
    def queued_count(self) -> int:
        """新規キュー登録件数を返す。"""

        return sum(
            result.was_enqueued
            for result in self.queue_results
        )

    @property
    def existing_order_count(self) -> int:
        """既存注文を再利用した件数を返す。"""

        return sum(
            result.was_existing
            for result in self.queue_results
        )

    @property
    def queue_failure_count(self) -> int:
        """注文キュー登録失敗件数を返す。"""

        return sum(
            result.is_failed
            for result in self.queue_results
        )

    @property
    def execution_count(self) -> int:
        """保存された約定件数を返す。"""

        if self.execution_result is None:
            return 0

        return self.execution_result.saved_execution_count

    @property
    def execution_failure_count(self) -> int:
        """注文執行失敗件数を返す。"""

        if self.execution_result is None:
            return 0

        return self.execution_result.failed_count

    @property
    def portfolio_update_count(self) -> int:
        """資産状態へ反映した約定件数を返す。"""

        if self.portfolio_result is None:
            return 0

        return self.portfolio_result.applied_count

    @property
    def equity_curve_report(
        self,
    ) -> EquityCurveReport | None:
        """最終エクイティカーブを返す。"""

        if self.portfolio_result is None:
            return None

        return self.portfolio_result.latest_equity_curve


class BacktestRunner:
    """戦略実行から資産曲線更新までを統括する。"""

    def __init__(
        self,
        *,
        session: BacktestSession,
        order_queue_service: BacktestOrderQueueService,
        queue_execution_service: BacktestQueueExecutionService,
        portfolio_update_service: BacktestPortfolioUpdateService,
    ) -> None:
        """バックテスト各工程のServiceを設定する。"""

        self.session = session
        self.order_queue_service = order_queue_service
        self.queue_execution_service = queue_execution_service
        self.portfolio_update_service = portfolio_update_service

    def run(
        self,
        *,
        order_type: OrderType = OrderType.MARKET,
        limit_price: float | None = None,
        stop_price: float | None = None,
        equity_curve_limit: int = 10_000,
        continue_on_error: bool = False,
    ) -> BacktestRunResult:
        """バックテスト全工程を順番に実行する。"""

        if equity_curve_limit <= 0:
            raise ValueError(
                "取得件数は0より大きい必要があります。"
            )

        try:
            session_result = self.session.run(
                continue_on_error=False
            )

            queue_results = (
                self.order_queue_service.enqueue_signals(
                    session_result.signals,
                    order_type=order_type,
                    limit_price=limit_price,
                    stop_price=stop_price,
                    continue_on_error=continue_on_error,
                )
            )

            if (
                not continue_on_error
                and any(
                    result.is_failed
                    for result in queue_results
                )
            ):
                failed = next(
                    result
                    for result in queue_results
                    if result.is_failed
                )
                raise RuntimeError(
                    failed.message
                    or "注文キュー登録に失敗しました。"
                )

            execution_result = (
                self.queue_execution_service.execute_all(
                    continue_on_error=continue_on_error,
                )
            )

            if (
                not continue_on_error
                and execution_result.failed_count > 0
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

            execution_records = tuple(
                item.execution_record
                for item in execution_result.items
                if item.execution_record is not None
            )

            portfolio_result = (
                self.portfolio_update_service.apply_executions(
                    execution_records,
                    equity_curve_limit=equity_curve_limit,
                )
            )

            return BacktestRunResult(
                status=BacktestRunStatus.COMPLETED,
                session_result=session_result,
                queue_results=queue_results,
                execution_result=execution_result,
                portfolio_result=portfolio_result,
                error_message=None,
            )

        except Exception as error:
            if not continue_on_error:
                raise

            return BacktestRunResult(
                status=BacktestRunStatus.FAILED,
                session_result=None,
                queue_results=(),
                execution_result=None,
                portfolio_result=None,
                error_message=str(error),
            )
