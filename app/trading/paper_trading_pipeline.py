"""ORBシグナル生成からPaper Broker執行・レポートまで統合する。"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

from app.market.models import StockPrice
from app.trading.execution_engine import (
    ExecutionBatchResult,
    ExecutionDecision,
    ExecutionEngine,
    ExecutionItemResult,
)
from app.trading.execution_report import (
    ExecutionReport,
    ExecutionReportService,
)
from app.trading.execution_risk import (
    ExecutionRiskDecision,
    ExecutionRiskResult,
    ExecutionRiskService,
)
from app.trading.order_models import (
    OrderType,
)
from app.trading.orb_signal_service import (
    OrbSignalGenerationResult,
    OrbSignalGenerationService,
)
from app.trading.signal_models import (
    TradeSignalRecord,
)


class SignalCanceller(Protocol):
    """リスク拒否されたシグナルの取消処理。"""

    def cancel(
        self,
        signal_id: str,
        *,
        process_note: str | None = None,
    ) -> TradeSignalRecord:
        """シグナルを取消済みに更新する。"""


@dataclass(frozen=True, slots=True)
class PaperTradingPipelineResult:
    """Paper Trading統合パイプラインの実行結果。"""

    signal_generation_result: OrbSignalGenerationResult
    risk_results: tuple[
        ExecutionRiskResult,
        ...
    ]
    execution_batch_result: ExecutionBatchResult
    execution_report: ExecutionReport
    report_csv_path: Path | None

    @property
    def generated_signal_count(self) -> int:
        """生成したシグナル数を返す。"""

        return (
            self.signal_generation_result
            .generated_count
        )

    @property
    def saved_signal_count(self) -> int:
        """新規保存したシグナル数を返す。"""

        return (
            self.signal_generation_result
            .saved_count
        )

    @property
    def duplicate_signal_count(self) -> int:
        """重複として保存しなかったシグナル数を返す。"""

        return (
            self.signal_generation_result
            .duplicate_count
        )

    @property
    def approved_count(self) -> int:
        """リスク判定で承認された件数を返す。"""

        return sum(
            result.decision
            is ExecutionRiskDecision.APPROVED
            for result in self.risk_results
        )

    @property
    def rejected_count(self) -> int:
        """リスク判定で拒否された件数を返す。"""

        return sum(
            result.decision
            is ExecutionRiskDecision.REJECTED
            for result in self.risk_results
        )

    @property
    def risk_failed_count(self) -> int:
        """リスク判定自体に失敗した件数を返す。"""

        return sum(
            result.decision
            is ExecutionRiskDecision.FAILED
            for result in self.risk_results
        )

    @property
    def executed_count(self) -> int:
        """Broker同期まで到達した件数を返す。"""

        return (
            self.execution_batch_result
            .executed_count
        )

    @property
    def failed_count(self) -> int:
        """統合処理で失敗した件数を返す。"""

        return (
            self.execution_batch_result
            .failed_count
        )

    @property
    def is_successful(self) -> bool:
        """保存失敗・リスク失敗・執行失敗がないか返す。"""

        return (
            self.signal_generation_result
            .is_successful
            and self.risk_failed_count == 0
            and self.failed_count == 0
        )


class PaperTradingPipeline:
    """ORBデータからPaper Broker執行までを統合する。"""

    def __init__(
        self,
        *,
        signal_generation_service: OrbSignalGenerationService,
        risk_service: ExecutionRiskService,
        execution_engine: ExecutionEngine,
        signal_repository: SignalCanceller,
        report_service: ExecutionReportService | None = None,
    ) -> None:
        """統合処理に必要なサービスを設定する。"""

        self.signal_generation_service = (
            signal_generation_service
        )
        self.risk_service = risk_service
        self.execution_engine = execution_engine
        self.signal_repository = signal_repository
        self.report_service = (
            report_service
            if report_service is not None
            else ExecutionReportService()
        )

    def run(
        self,
        prices: list[StockPrice],
        *,
        order_type: OrderType = OrderType.MARKET,
        limit_price: float | None = None,
        stop_price: float | None = None,
        report_generated_at: datetime | None = None,
        report_csv_path: Path | None = None,
        continue_on_error: bool = True,
    ) -> PaperTradingPipelineResult:
        """ORBシグナル生成から注文執行・レポートまで実行する。"""

        signal_generation_result = (
            self.signal_generation_service.run(
                prices,
                continue_on_error=continue_on_error,
            )
        )

        risk_results: list[
            ExecutionRiskResult
        ] = []

        execution_items: list[
            ExecutionItemResult
        ] = []

        for signal_record in (
            signal_generation_result.saved_records
        ):
            try:
                risk_result = self.risk_service.evaluate(
                    signal_record.signal,
                    continue_on_error=continue_on_error,
                )

            except Exception as error:
                if not continue_on_error:
                    raise

                execution_items.append(
                    self._create_failed_item(
                        signal_record=signal_record,
                        message=str(error),
                    )
                )
                continue

            risk_results.append(
                risk_result
            )

            if (
                risk_result.decision
                is ExecutionRiskDecision.APPROVED
            ):
                try:
                    execution_item = (
                        self.execution_engine.execute_signal(
                            signal_record.signal_id,
                            order_type=order_type,
                            limit_price=limit_price,
                            stop_price=stop_price,
                        )
                    )

                except Exception as error:
                    if not continue_on_error:
                        raise

                    execution_item = self._create_failed_item(
                        signal_record=signal_record,
                        message=str(error),
                    )

                execution_items.append(
                    execution_item
                )
                continue

            if (
                risk_result.decision
                is ExecutionRiskDecision.REJECTED
            ):
                cancelled_record = (
                    self.signal_repository.cancel(
                        signal_record.signal_id,
                        process_note=(
                            risk_result.message
                            or "execution risk rejected"
                        ),
                    )
                )

                execution_items.append(
                    self._create_failed_item(
                        signal_record=cancelled_record,
                        message=(
                            risk_result.message
                            or "execution risk rejected"
                        ),
                    )
                )
                continue

            execution_items.append(
                self._create_failed_item(
                    signal_record=signal_record,
                    message=(
                        risk_result.message
                        or "execution risk evaluation failed"
                    ),
                )
            )

        for failure in signal_generation_result.failures:
            execution_items.append(
                ExecutionItemResult(
                    decision=ExecutionDecision.FAILED,
                    signal_id=failure.signal_id,
                    order_id=None,
                    signal_record=None,
                    order_record=None,
                    order_creation_result=None,
                    broker_sync_result=None,
                    message=failure.message,
                )
            )

        execution_batch_result = ExecutionBatchResult(
            items=tuple(
                execution_items
            )
        )

        execution_report = self.report_service.create(
            execution_batch_result,
            generated_at=report_generated_at,
        )

        resolved_report_csv_path: Path | None = None

        if report_csv_path is not None:
            resolved_report_csv_path = (
                self.report_service.write_csv(
                    execution_report,
                    report_csv_path,
                )
            )

        return PaperTradingPipelineResult(
            signal_generation_result=(
                signal_generation_result
            ),
            risk_results=tuple(
                risk_results
            ),
            execution_batch_result=(
                execution_batch_result
            ),
            execution_report=execution_report,
            report_csv_path=(
                resolved_report_csv_path
            ),
        )

    @staticmethod
    def _create_failed_item(
        *,
        signal_record: TradeSignalRecord,
        message: str,
    ) -> ExecutionItemResult:
        """シグナル処理失敗をExecution明細へ変換する。"""

        return ExecutionItemResult(
            decision=ExecutionDecision.FAILED,
            signal_id=signal_record.signal_id,
            order_id=None,
            signal_record=signal_record,
            order_record=None,
            order_creation_result=None,
            broker_sync_result=None,
            message=message,
        )