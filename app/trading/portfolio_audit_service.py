"""Brokerとローカルの口座・ポジション差異を監査する。"""

from __future__ import annotations

from typing import Protocol

from app.trading.broker_adapter import (
    BrokerAccountSnapshot,
    BrokerPosition,
    BrokerPositionSide,
)
from app.trading.portfolio_audit_models import (
    PortfolioAuditIssue,
    PortfolioAuditIssueType,
    PortfolioAuditReport,
    PortfolioAuditSeverity,
    PortfolioAuditTolerance,
)
from app.trading.portfolio_models import PortfolioSnapshot
from app.trading.position_models import TradingPositionRecord


class PortfolioAuditPositionReader(Protocol):
    def list_recent(
        self,
        *,
        limit: int = 100,
        code: str | None = None,
        side: BrokerPositionSide | None = None,
    ) -> list[TradingPositionRecord]:
        """ローカル現在ポジションを返す。"""


class PortfolioAuditBrokerReader(Protocol):
    def get_account(self) -> BrokerAccountSnapshot:
        """Broker口座情報を返す。"""

    def list_positions(self) -> list[BrokerPosition]:
        """Brokerポジション一覧を返す。"""


class PortfolioAuditService:
    """修復を行わず、Brokerとローカル状態の差異を報告する。"""

    def __init__(
        self,
        *,
        position_repository: PortfolioAuditPositionReader,
        broker: PortfolioAuditBrokerReader,
        tolerance: PortfolioAuditTolerance | None = None,
    ) -> None:
        self.position_repository = position_repository
        self.broker = broker
        self.tolerance = (
            tolerance
            if tolerance is not None
            else PortfolioAuditTolerance()
        )

    def audit(
        self,
        *,
        local_portfolio: PortfolioSnapshot | None = None,
    ) -> PortfolioAuditReport:
        account = self.broker.get_account()
        broker_positions = self.broker.list_positions()
        local_positions = self.position_repository.list_recent(
            limit=10_000,
        )

        issues = self._audit_positions(
            local_positions=local_positions,
            broker_positions=broker_positions,
        )

        if local_portfolio is not None:
            issues.extend(
                self._audit_account(
                    local_portfolio=local_portfolio,
                    broker_account=account,
                )
            )

        return PortfolioAuditReport(
            issues=tuple(issues)
        )

    def _audit_positions(
        self,
        *,
        local_positions: list[TradingPositionRecord],
        broker_positions: list[BrokerPosition],
    ) -> list[PortfolioAuditIssue]:
        issues: list[PortfolioAuditIssue] = []

        local_map = {
            (record.code, record.side): record
            for record in local_positions
        }
        broker_map = {
            (position.code, position.side): position
            for position in broker_positions
        }

        identities = sorted(
            set(local_map) | set(broker_map),
            key=lambda item: (item[0], item[1].value),
        )

        for code, side in identities:
            local = local_map.get((code, side))
            broker = broker_map.get((code, side))

            if local is None:
                assert broker is not None
                issues.append(
                    PortfolioAuditIssue(
                        issue_type=(
                            PortfolioAuditIssueType
                            .BROKER_POSITION_MISSING_LOCALLY
                        ),
                        severity=PortfolioAuditSeverity.ERROR,
                        message="Brokerにのみポジションが存在します。",
                        code=code,
                        side=side,
                        local_value=None,
                        broker_value=broker.quantity,
                    )
                )
                continue

            if broker is None:
                issues.append(
                    PortfolioAuditIssue(
                        issue_type=(
                            PortfolioAuditIssueType
                            .LOCAL_POSITION_MISSING_AT_BROKER
                        ),
                        severity=PortfolioAuditSeverity.ERROR,
                        message="ローカルにのみポジションが存在します。",
                        code=code,
                        side=side,
                        local_value=local.quantity,
                        broker_value=None,
                    )
                )
                continue

            if local.quantity != broker.quantity:
                issues.append(
                    PortfolioAuditIssue(
                        issue_type=(
                            PortfolioAuditIssueType.QUANTITY_MISMATCH
                        ),
                        severity=PortfolioAuditSeverity.ERROR,
                        message=(
                            "ローカルとBrokerの保有数量が"
                            "一致しません。"
                        ),
                        code=code,
                        side=side,
                        local_value=local.quantity,
                        broker_value=broker.quantity,
                    )
                )

            if (
                abs(
                    local.position.average_cost
                    - broker.average_price
                )
                > self.tolerance.price_absolute
            ):
                issues.append(
                    PortfolioAuditIssue(
                        issue_type=(
                            PortfolioAuditIssueType
                            .AVERAGE_PRICE_MISMATCH
                        ),
                        severity=PortfolioAuditSeverity.WARNING,
                        message=(
                            "ローカルとBrokerの平均取得価格が"
                            "許容差を超えています。"
                        ),
                        code=code,
                        side=side,
                        local_value=local.position.average_cost,
                        broker_value=broker.average_price,
                    )
                )

        return issues

    def _audit_account(
        self,
        *,
        local_portfolio: PortfolioSnapshot,
        broker_account: BrokerAccountSnapshot,
    ) -> list[PortfolioAuditIssue]:
        checks = (
            (
                PortfolioAuditIssueType.CASH_BALANCE_MISMATCH,
                "現金残高",
                local_portfolio.cash_balance,
                broker_account.cash_balance,
            ),
            (
                PortfolioAuditIssueType.BUYING_POWER_MISMATCH,
                "買付余力",
                local_portfolio.buying_power,
                broker_account.buying_power,
            ),
            (
                PortfolioAuditIssueType.MARKET_VALUE_MISMATCH,
                "保有時価総額",
                local_portfolio.broker_market_value,
                broker_account.market_value,
            ),
            (
                PortfolioAuditIssueType.EQUITY_MISMATCH,
                "純資産額",
                local_portfolio.broker_equity,
                broker_account.equity,
            ),
        )

        issues: list[PortfolioAuditIssue] = []

        for issue_type, label, local_value, broker_value in checks:
            if (
                abs(local_value - broker_value)
                <= self.tolerance.money_absolute
            ):
                continue

            issues.append(
                PortfolioAuditIssue(
                    issue_type=issue_type,
                    severity=PortfolioAuditSeverity.ERROR,
                    message=(
                        f"ローカルとBrokerの{label}が"
                        "許容差を超えています。"
                    ),
                    local_value=local_value,
                    broker_value=broker_value,
                )
            )

        return issues
