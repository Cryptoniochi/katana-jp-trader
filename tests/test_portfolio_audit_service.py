"""PortfolioAuditServiceのテスト。"""

from __future__ import annotations

from datetime import datetime, timezone

from app.trading.broker_adapter import (
    BrokerAccountSnapshot,
    BrokerPosition,
    BrokerPositionSide,
)
from app.trading.portfolio_audit_models import (
    PortfolioAuditIssueType,
    PortfolioAuditTolerance,
)
from app.trading.portfolio_audit_service import (
    PortfolioAuditService,
)
from app.trading.portfolio_models import PortfolioSnapshot
from app.trading.position_models import (
    TradingPosition,
    TradingPositionRecord,
)


NOW = datetime(
    2026,
    7,
    17,
    6,
    0,
    tzinfo=timezone.utc,
)


def local_position(
    *,
    code: str = "7203",
    quantity: int = 100,
    average_cost: float = 2500.0,
) -> TradingPositionRecord:
    return TradingPositionRecord(
        id=1,
        position=TradingPosition(
            position_id=f"position-{code}-long",
            code=code,
            side=BrokerPositionSide.LONG,
            quantity=quantity,
            average_cost=average_cost,
            realized_profit_loss=0.0,
            opened_at=NOW,
        ),
        created_at=NOW,
        updated_at=NOW,
    )


def broker_position(
    *,
    code: str = "7203",
    quantity: int = 100,
    average_price: float = 2500.0,
) -> BrokerPosition:
    return BrokerPosition(
        code=code,
        side=BrokerPositionSide.LONG,
        quantity=quantity,
        average_price=average_price,
        market_price=2600.0,
        updated_at=NOW,
    )


def account(
    *,
    cash: float = 750_000.0,
    buying_power: float = 750_000.0,
    market_value: float = 260_000.0,
    equity: float = 1_010_000.0,
) -> BrokerAccountSnapshot:
    return BrokerAccountSnapshot(
        currency="JPY",
        cash_balance=cash,
        buying_power=buying_power,
        market_value=market_value,
        equity=equity,
        updated_at=NOW,
    )


def local_portfolio(
    *,
    cash: float = 750_000.0,
    buying_power: float = 750_000.0,
    market_value: float = 260_000.0,
    equity: float = 1_010_000.0,
) -> PortfolioSnapshot:
    return PortfolioSnapshot(
        currency="JPY",
        cash_balance=cash,
        buying_power=buying_power,
        broker_market_value=market_value,
        broker_equity=equity,
        positions=(),
        generated_at=NOW,
    )


class FakePositionRepository:
    def __init__(
        self,
        positions: list[TradingPositionRecord],
    ) -> None:
        self.positions = positions

    def list_recent(
        self,
        *,
        limit: int = 100,
        code=None,
        side=None,
    ) -> list[TradingPositionRecord]:
        return list(self.positions)


class FakeBroker:
    def __init__(
        self,
        *,
        positions: list[BrokerPosition],
        broker_account: BrokerAccountSnapshot | None = None,
    ) -> None:
        self.positions = positions
        self.broker_account = (
            broker_account
            if broker_account is not None
            else account()
        )

    def get_account(self) -> BrokerAccountSnapshot:
        return self.broker_account

    def list_positions(self) -> list[BrokerPosition]:
        return list(self.positions)


def audit(
    *,
    local_positions: list[TradingPositionRecord],
    broker_positions: list[BrokerPosition],
    portfolio: PortfolioSnapshot | None = None,
    tolerance: PortfolioAuditTolerance | None = None,
):
    return PortfolioAuditService(
        position_repository=FakePositionRepository(
            local_positions
        ),
        broker=FakeBroker(
            positions=broker_positions
        ),
        tolerance=tolerance,
    ).audit(
        local_portfolio=portfolio
    )


def test_consistent_positions_return_empty_report() -> None:
    report = audit(
        local_positions=[local_position()],
        broker_positions=[broker_position()],
        portfolio=local_portfolio(),
    )

    assert report.is_consistent
    assert report.issue_count == 0


def test_detects_broker_only_position() -> None:
    report = audit(
        local_positions=[],
        broker_positions=[broker_position()],
    )

    assert report.has_errors
    assert report.issues[0].issue_type is (
        PortfolioAuditIssueType
        .BROKER_POSITION_MISSING_LOCALLY
    )


def test_detects_local_only_position() -> None:
    report = audit(
        local_positions=[local_position()],
        broker_positions=[],
    )

    assert report.issues[0].issue_type is (
        PortfolioAuditIssueType
        .LOCAL_POSITION_MISSING_AT_BROKER
    )


def test_detects_quantity_mismatch() -> None:
    report = audit(
        local_positions=[
            local_position(quantity=100)
        ],
        broker_positions=[
            broker_position(quantity=80)
        ],
    )

    assert report.error_count == 1
    assert report.issues[0].issue_type is (
        PortfolioAuditIssueType.QUANTITY_MISMATCH
    )


def test_detects_average_price_mismatch_as_warning() -> None:
    report = audit(
        local_positions=[
            local_position(average_cost=2500.0)
        ],
        broker_positions=[
            broker_position(average_price=2501.0)
        ],
        tolerance=PortfolioAuditTolerance(
            price_absolute=0.1
        ),
    )

    assert report.warning_count == 1
    assert report.error_count == 0
    assert report.issues[0].issue_type is (
        PortfolioAuditIssueType
        .AVERAGE_PRICE_MISMATCH
    )


def test_average_price_within_tolerance_is_ignored() -> None:
    report = audit(
        local_positions=[
            local_position(average_cost=2500.0)
        ],
        broker_positions=[
            broker_position(average_price=2500.05)
        ],
        tolerance=PortfolioAuditTolerance(
            price_absolute=0.1
        ),
    )

    assert report.is_consistent


def test_detects_account_value_mismatches() -> None:
    report = audit(
        local_positions=[],
        broker_positions=[],
        portfolio=local_portfolio(
            cash=700_000.0,
            buying_power=700_000.0,
            market_value=200_000.0,
            equity=900_000.0,
        ),
    )

    assert report.error_count == 4
    assert {
        issue.issue_type
        for issue in report.issues
    } == {
        PortfolioAuditIssueType.CASH_BALANCE_MISMATCH,
        PortfolioAuditIssueType.BUYING_POWER_MISMATCH,
        PortfolioAuditIssueType.MARKET_VALUE_MISMATCH,
        PortfolioAuditIssueType.EQUITY_MISMATCH,
    }


def test_account_values_within_tolerance_are_ignored() -> None:
    report = audit(
        local_positions=[],
        broker_positions=[],
        portfolio=local_portfolio(
            cash=750_000.5,
            buying_power=750_000.5,
            market_value=260_000.5,
            equity=1_010_000.5,
        ),
        tolerance=PortfolioAuditTolerance(
            money_absolute=1.0
        ),
    )

    assert report.is_consistent
