"""Project KATANAのリスク判定を統合するサービス。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from app.risk.consecutive_loss_models import (
    ConsecutiveLossEvaluation,
    ConsecutiveLossSnapshot,
    ConsecutiveLossStatus,
)
from app.risk.consecutive_loss_service import ConsecutiveLossService
from app.risk.daily_loss_models import (
    DailyLossEvaluation,
    DailyLossSnapshot,
    DailyLossStatus,
)
from app.risk.daily_loss_service import DailyLossService
from app.risk.kill_switch_models import (
    KillSwitchEvaluation,
    KillSwitchSnapshot,
    KillSwitchStatus,
)
from app.risk.kill_switch_service import KillSwitchService
from app.risk.position_sizing_models import (
    PositionSizingRequest,
    PositionSizingResult,
    PositionSizingStatus,
)
from app.risk.position_sizing_service import PositionSizingService
from app.risk.risk_report_models import (
    RiskReport,
    RiskReportItem,
    RiskReportReason,
    RiskReportSnapshot,
    RiskReportStatus,
)
from app.risk.risk_report_service import RiskReportService


@dataclass(frozen=True, slots=True)
class RiskEngineRequest:
    """統合リスク判定への入力。"""

    trading_date: date
    position_sizing_request: PositionSizingRequest
    daily_loss_snapshot: DailyLossSnapshot
    consecutive_loss_snapshot: ConsecutiveLossSnapshot
    manual_blocked: bool = False
    runtime_health_ok: bool = True
    heartbeat_alive: bool = True
    broker_available: bool = True
    evaluated_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def __post_init__(self) -> None:
        """入力間の取引日を検証し、評価時刻をUTCへ正規化する。"""

        if self.daily_loss_snapshot.trading_date != self.trading_date:
            raise ValueError(
                "daily_loss_snapshotのtrading_dateが一致しません。"
            )

        if (
            self.consecutive_loss_snapshot.trading_date
            != self.trading_date
        ):
            raise ValueError(
                "consecutive_loss_snapshotのtrading_dateが一致しません。"
            )

        if self.evaluated_at.tzinfo is None:
            normalized = self.evaluated_at.replace(
                tzinfo=timezone.utc
            )
        else:
            normalized = self.evaluated_at.astimezone(
                timezone.utc
            )

        object.__setattr__(
            self,
            "evaluated_at",
            normalized,
        )


@dataclass(frozen=True, slots=True)
class RiskEngineResult:
    """統合リスク判定の結果。"""

    position_sizing: PositionSizingResult
    daily_loss: DailyLossEvaluation
    consecutive_loss: ConsecutiveLossEvaluation
    kill_switch: KillSwitchEvaluation
    risk_report: RiskReport

    @property
    def allows_new_entries(self) -> bool:
        """新規エントリーを許可するか返す。"""

        return self.risk_report.allows_new_entries

    @property
    def is_blocked(self) -> bool:
        """総合リスク判定が停止状態か返す。"""

        return self.risk_report.is_blocked

    @property
    def approved_quantity(self) -> int:
        """Position Sizingで承認された数量を返す。"""

        if self.is_blocked:
            return 0

        return self.position_sizing.approved_quantity


class RiskEngine:
    """各リスクサービスを順番に評価して統合レポートを返す。"""

    def __init__(
        self,
        *,
        position_sizing_service: PositionSizingService,
        daily_loss_service: DailyLossService,
        consecutive_loss_service: ConsecutiveLossService,
        kill_switch_service: KillSwitchService,
        risk_report_service: RiskReportService,
    ) -> None:
        """Risk Engineを構成する各サービスを設定する。"""

        self.position_sizing_service = position_sizing_service
        self.daily_loss_service = daily_loss_service
        self.consecutive_loss_service = consecutive_loss_service
        self.kill_switch_service = kill_switch_service
        self.risk_report_service = risk_report_service

    def evaluate(
        self,
        request: RiskEngineRequest,
    ) -> RiskEngineResult:
        """すべてのリスク制約を評価して統合結果を返す。"""

        position_sizing = self.position_sizing_service.calculate(
            request.position_sizing_request
        )
        daily_loss = self.daily_loss_service.evaluate(
            request.daily_loss_snapshot
        )
        consecutive_loss = (
            self.consecutive_loss_service.evaluate(
                request.consecutive_loss_snapshot
            )
        )

        kill_switch = self.kill_switch_service.evaluate(
            KillSwitchSnapshot(
                manual_blocked=request.manual_blocked,
                daily_loss_blocked=daily_loss.is_blocked,
                consecutive_loss_blocked=(
                    consecutive_loss.is_blocked
                ),
                runtime_health_ok=request.runtime_health_ok,
                heartbeat_alive=request.heartbeat_alive,
                broker_available=request.broker_available,
                evaluated_at=request.evaluated_at,
            )
        )

        risk_report = self.risk_report_service.generate(
            RiskReportSnapshot(
                trading_date=request.trading_date,
                items=self._build_report_items(
                    position_sizing=position_sizing,
                    daily_loss=daily_loss,
                    consecutive_loss=consecutive_loss,
                    kill_switch=kill_switch,
                    runtime_health_ok=request.runtime_health_ok,
                    heartbeat_alive=request.heartbeat_alive,
                    broker_available=request.broker_available,
                ),
                generated_at=request.evaluated_at,
                metadata={
                    "requested_quantity": (
                        position_sizing.requested_quantity
                    ),
                    "approved_quantity": (
                        position_sizing.approved_quantity
                    ),
                },
            )
        )

        return RiskEngineResult(
            position_sizing=position_sizing,
            daily_loss=daily_loss,
            consecutive_loss=consecutive_loss,
            kill_switch=kill_switch,
            risk_report=risk_report,
        )

    def allows_new_entries(
        self,
        request: RiskEngineRequest,
    ) -> bool:
        """新規エントリーを許可するか返す。"""

        return self.evaluate(
            request
        ).allows_new_entries

    def _build_report_items(
        self,
        *,
        position_sizing: PositionSizingResult,
        daily_loss: DailyLossEvaluation,
        consecutive_loss: ConsecutiveLossEvaluation,
        kill_switch: KillSwitchEvaluation,
        runtime_health_ok: bool,
        heartbeat_alive: bool,
        broker_available: bool,
    ) -> tuple[RiskReportItem, ...]:
        """個別判定から統合レポート項目を生成する。"""

        return (
            self._position_sizing_item(position_sizing),
            self._daily_loss_item(daily_loss),
            self._consecutive_loss_item(consecutive_loss),
            self._runtime_health_item(runtime_health_ok),
            self._heartbeat_item(heartbeat_alive),
            self._broker_item(broker_available),
            self._kill_switch_item(kill_switch),
        )

    @staticmethod
    def _position_sizing_item(
        result: PositionSizingResult,
    ) -> RiskReportItem:
        """Position Sizing結果をレポート項目へ変換する。"""

        metadata = {
            "requested_quantity": result.requested_quantity,
            "approved_quantity": result.approved_quantity,
            "approved_order_value": result.approved_order_value,
            "reason": result.reason.value,
        }

        if result.status is PositionSizingStatus.REJECTED:
            return RiskReportItem(
                name="position_sizing",
                status=RiskReportStatus.BLOCKED,
                reason=RiskReportReason.POSITION_SIZE_REJECTED,
                message="Position Sizingにより注文が拒否されました。",
                blocks_new_entries=True,
                metadata=metadata,
            )

        if result.status is PositionSizingStatus.REDUCED:
            return RiskReportItem(
                name="position_sizing",
                status=RiskReportStatus.WARNING,
                reason=RiskReportReason.POSITION_SIZE_REDUCED,
                message="Position Sizingにより注文数量が縮小されました。",
                blocks_new_entries=False,
                metadata=metadata,
            )

        return RiskReportItem(
            name="position_sizing",
            status=RiskReportStatus.CLEAR,
            reason=RiskReportReason.ALL_CLEAR,
            message="Position Sizingは制約内です。",
            blocks_new_entries=False,
            metadata=metadata,
        )

    @staticmethod
    def _daily_loss_item(
        evaluation: DailyLossEvaluation,
    ) -> RiskReportItem:
        """Daily Loss結果をレポート項目へ変換する。"""

        metadata = {
            "total_loss": evaluation.total_loss,
            "max_daily_loss": evaluation.max_daily_loss,
            "remaining_loss_capacity": (
                evaluation.remaining_loss_capacity
            ),
            "reason": evaluation.reason.value,
        }

        if evaluation.status is DailyLossStatus.BLOCKED:
            return RiskReportItem(
                name="daily_loss",
                status=RiskReportStatus.BLOCKED,
                reason=RiskReportReason.DAILY_LOSS_BLOCKED,
                message="日次損失制限により新規注文を停止しています。",
                blocks_new_entries=True,
                metadata=metadata,
            )

        if evaluation.status is DailyLossStatus.WARNING:
            return RiskReportItem(
                name="daily_loss",
                status=RiskReportStatus.WARNING,
                reason=RiskReportReason.DAILY_LOSS_WARNING,
                message="日次損失が警告水準に到達しています。",
                blocks_new_entries=False,
                metadata=metadata,
            )

        return RiskReportItem(
            name="daily_loss",
            status=RiskReportStatus.CLEAR,
            reason=RiskReportReason.ALL_CLEAR,
            message="日次損失は制限内です。",
            blocks_new_entries=False,
            metadata=metadata,
        )

    @staticmethod
    def _consecutive_loss_item(
        evaluation: ConsecutiveLossEvaluation,
    ) -> RiskReportItem:
        """Consecutive Loss結果をレポート項目へ変換する。"""

        metadata = {
            "consecutive_losses": evaluation.consecutive_losses,
            "max_consecutive_losses": (
                evaluation.max_consecutive_losses
            ),
            "remaining_losses_before_block": (
                evaluation.remaining_losses_before_block
            ),
            "reason": evaluation.reason.value,
        }

        if evaluation.status is ConsecutiveLossStatus.BLOCKED:
            return RiskReportItem(
                name="consecutive_loss",
                status=RiskReportStatus.BLOCKED,
                reason=(
                    RiskReportReason.CONSECUTIVE_LOSS_BLOCKED
                ),
                message="連敗制限により新規注文を停止しています。",
                blocks_new_entries=True,
                metadata=metadata,
            )

        if evaluation.status is ConsecutiveLossStatus.WARNING:
            return RiskReportItem(
                name="consecutive_loss",
                status=RiskReportStatus.WARNING,
                reason=(
                    RiskReportReason.CONSECUTIVE_LOSS_WARNING
                ),
                message="連敗数が警告水準に到達しています。",
                blocks_new_entries=False,
                metadata=metadata,
            )

        return RiskReportItem(
            name="consecutive_loss",
            status=RiskReportStatus.CLEAR,
            reason=RiskReportReason.ALL_CLEAR,
            message="連敗数は制限内です。",
            blocks_new_entries=False,
            metadata=metadata,
        )

    @staticmethod
    def _runtime_health_item(
        runtime_health_ok: bool,
    ) -> RiskReportItem:
        """Runtime Health状態をレポート項目へ変換する。"""

        if runtime_health_ok:
            return RiskReportItem(
                name="runtime_health",
                status=RiskReportStatus.CLEAR,
                reason=RiskReportReason.ALL_CLEAR,
                message="Runtime Healthは正常です。",
                blocks_new_entries=False,
            )

        return RiskReportItem(
            name="runtime_health",
            status=RiskReportStatus.BLOCKED,
            reason=RiskReportReason.RUNTIME_HEALTH_ERROR,
            message="Runtime Health異常により新規注文を停止しています。",
            blocks_new_entries=True,
        )

    @staticmethod
    def _heartbeat_item(
        heartbeat_alive: bool,
    ) -> RiskReportItem:
        """Heartbeat状態をレポート項目へ変換する。"""

        if heartbeat_alive:
            return RiskReportItem(
                name="heartbeat",
                status=RiskReportStatus.CLEAR,
                reason=RiskReportReason.ALL_CLEAR,
                message="Runtime Heartbeatは正常です。",
                blocks_new_entries=False,
            )

        return RiskReportItem(
            name="heartbeat",
            status=RiskReportStatus.BLOCKED,
            reason=RiskReportReason.HEARTBEAT_STALE,
            message="Runtime Heartbeat停止により新規注文を停止しています。",
            blocks_new_entries=True,
        )

    @staticmethod
    def _broker_item(
        broker_available: bool,
    ) -> RiskReportItem:
        """Broker状態をレポート項目へ変換する。"""

        if broker_available:
            return RiskReportItem(
                name="broker",
                status=RiskReportStatus.CLEAR,
                reason=RiskReportReason.ALL_CLEAR,
                message="Brokerは利用可能です。",
                blocks_new_entries=False,
            )

        return RiskReportItem(
            name="broker",
            status=RiskReportStatus.BLOCKED,
            reason=RiskReportReason.BROKER_UNAVAILABLE,
            message="Broker利用不可により新規注文を停止しています。",
            blocks_new_entries=True,
        )

    @staticmethod
    def _kill_switch_item(
        evaluation: KillSwitchEvaluation,
    ) -> RiskReportItem:
        """Kill Switch結果をレポート項目へ変換する。"""

        metadata = {
            "reason": evaluation.reason.value,
        }

        if evaluation.status is KillSwitchStatus.BLOCKED:
            return RiskReportItem(
                name="kill_switch",
                status=RiskReportStatus.BLOCKED,
                reason=RiskReportReason.KILL_SWITCH_BLOCKED,
                message="Kill Switchが新規注文を停止しています。",
                blocks_new_entries=True,
                metadata=metadata,
            )

        return RiskReportItem(
            name="kill_switch",
            status=RiskReportStatus.CLEAR,
            reason=RiskReportReason.ALL_CLEAR,
            message="Kill Switchは解除されています。",
            blocks_new_entries=False,
            metadata=metadata,
        )
