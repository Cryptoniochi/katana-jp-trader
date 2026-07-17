"""バックテスト約定をポジション・資産推移へ反映する。"""

from dataclasses import dataclass

from app.trading.equity_curve_models import EquityCurveReport
from app.trading.equity_curve_service import EquityCurveService
from app.trading.portfolio_models import PortfolioSnapshot
from app.trading.portfolio_repository import PortfolioRepository
from app.trading.portfolio_service import PortfolioService
from app.trading.position_service import (
    PositionApplicationResult,
    PositionService,
)
from app.trading.trade_execution_models import (
    TradeExecutionRecord,
)


@dataclass(frozen=True, slots=True)
class BacktestPortfolioUpdateResult:
    """1件の約定を資産状態へ反映した結果。"""

    execution_record: TradeExecutionRecord
    position_result: PositionApplicationResult
    portfolio_snapshot: PortfolioSnapshot
    equity_curve_report: EquityCurveReport

    @property
    def execution_id(self) -> str:
        """約定IDを返す。"""

        return self.execution_record.execution_id

    @property
    def position_was_applied(self) -> bool:
        """約定が新しくポジションへ反映されたか返す。"""

        return self.position_result.applied

    @property
    def position_closed(self) -> bool:
        """ポジションが全決済されたか返す。"""

        return self.position_result.position_closed


@dataclass(frozen=True, slots=True)
class BacktestPortfolioBatchUpdateResult:
    """複数約定の資産更新結果。"""

    items: tuple[
        BacktestPortfolioUpdateResult,
        ...
    ]

    @property
    def processed_count(self) -> int:
        """処理した約定件数を返す。"""

        return len(self.items)

    @property
    def applied_count(self) -> int:
        """新しくポジションへ反映した件数を返す。"""

        return sum(
            item.position_was_applied
            for item in self.items
        )

    @property
    def latest_snapshot(self) -> PortfolioSnapshot | None:
        """最後に保存したポートフォリオを返す。"""

        if not self.items:
            return None

        return self.items[-1].portfolio_snapshot

    @property
    def latest_equity_curve(
        self,
    ) -> EquityCurveReport | None:
        """最後に作成したエクイティカーブを返す。"""

        if not self.items:
            return None

        return self.items[-1].equity_curve_report


class BacktestPortfolioUpdateService:
    """約定から資産曲線までを順番に更新する。"""

    def __init__(
        self,
        *,
        position_service: PositionService,
        portfolio_service: PortfolioService,
        portfolio_repository: PortfolioRepository,
        equity_curve_service: EquityCurveService,
    ) -> None:
        """必要なServiceとRepositoryを設定する。"""

        self.position_service = position_service
        self.portfolio_service = portfolio_service
        self.portfolio_repository = portfolio_repository
        self.equity_curve_service = equity_curve_service

    def apply_execution(
        self,
        execution_record: TradeExecutionRecord,
        *,
        equity_curve_limit: int = 10_000,
    ) -> BacktestPortfolioUpdateResult:
        """1件の約定をポジション・資産推移へ反映する。"""

        if equity_curve_limit <= 0:
            raise ValueError(
                "取得件数は0より大きい必要があります。"
            )

        position_result = (
            self.position_service.apply_execution(
                execution_record
            )
        )

        snapshot = self.portfolio_service.create_snapshot(
            generated_at=(
                execution_record.execution.executed_at
            )
        )

        saved_snapshot = self.portfolio_repository.save(
            snapshot
        )

        report = self.equity_curve_service.create_report(
            limit=equity_curve_limit
        )

        return BacktestPortfolioUpdateResult(
            execution_record=execution_record,
            position_result=position_result,
            portfolio_snapshot=saved_snapshot,
            equity_curve_report=report,
        )

    def apply_executions(
        self,
        execution_records: tuple[
            TradeExecutionRecord,
            ...
        ],
        *,
        equity_curve_limit: int = 10_000,
    ) -> BacktestPortfolioBatchUpdateResult:
        """複数約定を渡された順番で反映する。"""

        if equity_curve_limit <= 0:
            raise ValueError(
                "取得件数は0より大きい必要があります。"
            )

        ordered_records = tuple(
            sorted(
                execution_records,
                key=lambda record: (
                    record.execution.executed_at,
                    record.execution_id,
                ),
            )
        )

        results = tuple(
            self.apply_execution(
                record,
                equity_curve_limit=equity_curve_limit,
            )
            for record in ordered_records
        )

        return BacktestPortfolioBatchUpdateResult(
            items=results
        )
