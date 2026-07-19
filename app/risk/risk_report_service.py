"""統合リスクレポートを生成するサービス。"""

from __future__ import annotations

from app.risk.risk_report_models import (
    RiskReport,
    RiskReportReason,
    RiskReportSnapshot,
    RiskReportStatus,
)


class RiskReportService:
    """複数のリスク項目から総合リスクレポートを生成する。"""

    def generate(
        self,
        snapshot: RiskReportSnapshot,
    ) -> RiskReport:
        """Snapshotを集約して統合リスクレポートを返す。"""

        warning_reasons = tuple(
            item.reason
            for item in snapshot.items
            if item.status is RiskReportStatus.WARNING
        )
        blocking_reasons = tuple(
            item.reason
            for item in snapshot.items
            if item.status is RiskReportStatus.BLOCKED
        )

        status, primary_reason = self._determine_status(
            warning_reasons=warning_reasons,
            blocking_reasons=blocking_reasons,
        )

        return RiskReport(
            trading_date=snapshot.trading_date,
            status=status,
            primary_reason=primary_reason,
            items=snapshot.items,
            warning_reasons=warning_reasons,
            blocking_reasons=blocking_reasons,
            generated_at=snapshot.generated_at,
            metadata=snapshot.metadata,
        )

    def allows_new_entries(
        self,
        snapshot: RiskReportSnapshot,
    ) -> bool:
        """新規エントリーを許可するか返す。"""

        return self.generate(
            snapshot
        ).allows_new_entries

    def is_blocked(
        self,
        snapshot: RiskReportSnapshot,
    ) -> bool:
        """総合リスク状態が停止中か返す。"""

        return self.generate(
            snapshot
        ).is_blocked

    def has_warning(
        self,
        snapshot: RiskReportSnapshot,
    ) -> bool:
        """警告または停止状態か返す。"""

        return self.generate(
            snapshot
        ).has_warning

    @staticmethod
    def _determine_status(
        *,
        warning_reasons: tuple[RiskReportReason, ...],
        blocking_reasons: tuple[RiskReportReason, ...],
    ) -> tuple[
        RiskReportStatus,
        RiskReportReason,
    ]:
        """警告理由と停止理由から総合状態を決定する。"""

        if blocking_reasons:
            return (
                RiskReportStatus.BLOCKED,
                blocking_reasons[0],
            )

        if warning_reasons:
            return (
                RiskReportStatus.WARNING,
                warning_reasons[0],
            )

        return (
            RiskReportStatus.CLEAR,
            RiskReportReason.ALL_CLEAR,
        )
