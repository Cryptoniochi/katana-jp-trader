"""Brokerとローカルポートフォリオ差異の監査モデル。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.trading.broker_adapter import BrokerPositionSide


class PortfolioAuditSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class PortfolioAuditIssueType(StrEnum):
    BROKER_POSITION_MISSING_LOCALLY = "broker_position_missing_locally"
    LOCAL_POSITION_MISSING_AT_BROKER = "local_position_missing_at_broker"
    QUANTITY_MISMATCH = "quantity_mismatch"
    AVERAGE_PRICE_MISMATCH = "average_price_mismatch"
    CASH_BALANCE_MISMATCH = "cash_balance_mismatch"
    BUYING_POWER_MISMATCH = "buying_power_mismatch"
    MARKET_VALUE_MISMATCH = "market_value_mismatch"
    EQUITY_MISMATCH = "equity_mismatch"


@dataclass(frozen=True, slots=True)
class PortfolioAuditTolerance:
    money_absolute: float = 1.0
    price_absolute: float = 0.01

    def __post_init__(self) -> None:
        if self.money_absolute < 0:
            raise ValueError("金額許容差は0以上である必要があります。")
        if self.price_absolute < 0:
            raise ValueError("価格許容差は0以上である必要があります。")


@dataclass(frozen=True, slots=True)
class PortfolioAuditIssue:
    issue_type: PortfolioAuditIssueType
    severity: PortfolioAuditSeverity
    message: str
    code: str | None = None
    side: BrokerPositionSide | None = None
    local_value: object | None = None
    broker_value: object | None = None

    def __post_init__(self) -> None:
        message = self.message.strip()
        if not message:
            raise ValueError("監査メッセージを指定してください。")

        code = None if self.code is None else self.code.strip()
        if code is not None and (
            not code.isdigit()
            or len(code) not in {4, 5}
        ):
            raise ValueError(
                "銘柄コードは4桁または5桁の数字で指定してください。"
            )

        object.__setattr__(self, "message", message)
        object.__setattr__(self, "code", code)


@dataclass(frozen=True, slots=True)
class PortfolioAuditReport:
    issues: tuple[PortfolioAuditIssue, ...]

    @property
    def issue_count(self) -> int:
        return len(self.issues)

    @property
    def warning_count(self) -> int:
        return sum(
            issue.severity is PortfolioAuditSeverity.WARNING
            for issue in self.issues
        )

    @property
    def error_count(self) -> int:
        return sum(
            issue.severity is PortfolioAuditSeverity.ERROR
            for issue in self.issues
        )

    @property
    def is_consistent(self) -> bool:
        return not self.issues

    @property
    def has_errors(self) -> bool:
        return self.error_count > 0
