"""PortfolioServiceの統合テスト。"""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.database import initialize_database
from app.trading.broker_adapter import (
    BrokerAccountSnapshot,
    BrokerPosition,
    BrokerPositionSide,
)
from app.trading.portfolio_service import (
    PortfolioConsistencyError,
    PortfolioPriceUnavailableError,
    PortfolioService,
)
from app.trading.position_models import TradingPosition
from app.trading.position_repository import PositionRepository


CURRENT_TIME = datetime(
    2026,
    7,
    20,
    1,
    0,
    tzinfo=timezone.utc,
)


class StaticBroker:
    """固定口座・ポジションを返すBroker。"""

    def __init__(
        self,
        *,
        positions: list[BrokerPosition],
        account: BrokerAccountSnapshot,
    ) -> None:
        self.positions = positions
        self.account = account

    def list_positions(self) -> list[BrokerPosition]:
        return list(self.positions)

    def get_account(self) -> BrokerAccountSnapshot:
        return self.account


def create_repository(
    tmp_path: Path,
) -> PositionRepository:
    """初期化済みPositionRepositoryを作成する。"""

    database_path = tmp_path / "katana.db"
    initialize_database(database_path)

    return PositionRepository(
        database_path,
        now_provider=lambda: CURRENT_TIME,
    )


def create_account(
    *,
    cash_balance: float = 750_000.0,
    buying_power: float = 750_000.0,
    market_value: float = 260_000.0,
    equity: float = 1_010_000.0,
) -> BrokerAccountSnapshot:
    """固定口座Snapshotを作成する。"""

    return BrokerAccountSnapshot(
        currency="JPY",
        cash_balance=cash_balance,
        buying_power=buying_power,
        market_value=market_value,
        equity=equity,
        updated_at=CURRENT_TIME,
    )


def create_local_position(
    repository: PositionRepository,
    *,
    quantity: int = 100,
    average_cost: float = 2500.0,
    realized_profit_loss: float = 5000.0,
) -> None:
    """ローカル現在ポジションを保存する。"""

    repository.create(
        TradingPosition(
            position_id="position-7203-long",
            code="7203",
            side=BrokerPositionSide.LONG,
            quantity=quantity,
            average_cost=average_cost,
            realized_profit_loss=realized_profit_loss,
            opened_at=CURRENT_TIME,
        )
    )


def create_broker_position(
    *,
    quantity: int = 100,
    average_price: float = 2500.0,
    market_price: float | None = 2600.0,
) -> BrokerPosition:
    """Broker現在ポジションを作成する。"""

    return BrokerPosition(
        code="7203",
        side=BrokerPositionSide.LONG,
        quantity=quantity,
        average_price=average_price,
        market_price=market_price,
        updated_at=CURRENT_TIME,
    )


def test_service_creates_portfolio_snapshot(
    tmp_path: Path,
) -> None:
    """現在ポジションと口座情報を集約する。"""

    repository = create_repository(tmp_path)
    create_local_position(repository)

    service = PortfolioService(
        position_repository=repository,
        broker=StaticBroker(
            positions=[create_broker_position()],
            account=create_account(),
        ),
    )

    snapshot = service.create_snapshot(
        generated_at=CURRENT_TIME
    )

    assert snapshot.currency == "JPY"
    assert snapshot.cash_balance == pytest.approx(
        750_000.0
    )
    assert snapshot.buying_power == pytest.approx(
        750_000.0
    )
    assert snapshot.position_count == 1
    assert snapshot.total_acquisition_value == pytest.approx(
        250_000.0
    )
    assert snapshot.total_market_value == pytest.approx(
        260_000.0
    )
    assert (
        snapshot.total_unrealized_profit_loss
        == pytest.approx(10_000.0)
    )
    assert snapshot.total_realized_profit_loss == pytest.approx(
        5000.0
    )
    assert snapshot.calculated_equity == pytest.approx(
        1_010_000.0
    )
    assert snapshot.broker_equity == pytest.approx(
        1_010_000.0
    )
    assert snapshot.generated_at == CURRENT_TIME


def test_service_returns_empty_portfolio(
    tmp_path: Path,
) -> None:
    """現在ポジションがなければ空の集計を返す。"""

    repository = create_repository(tmp_path)

    service = PortfolioService(
        position_repository=repository,
        broker=StaticBroker(
            positions=[],
            account=create_account(
                cash_balance=1_000_000.0,
                buying_power=1_000_000.0,
                market_value=0.0,
                equity=1_000_000.0,
            ),
        ),
    )

    snapshot = service.create_snapshot(
        generated_at=CURRENT_TIME
    )

    assert snapshot.position_count == 0
    assert snapshot.total_acquisition_value == 0
    assert snapshot.total_market_value == 0
    assert snapshot.total_unrealized_profit_loss == 0
    assert snapshot.total_realized_profit_loss == 0
    assert snapshot.calculated_equity == pytest.approx(
        1_000_000.0
    )


def test_service_rejects_missing_broker_position(
    tmp_path: Path,
) -> None:
    """Broker側に対応ポジションがなければ拒否する。"""

    repository = create_repository(tmp_path)
    create_local_position(repository)

    service = PortfolioService(
        position_repository=repository,
        broker=StaticBroker(
            positions=[],
            account=create_account(),
        ),
    )

    with pytest.raises(
        PortfolioConsistencyError,
        match="存在しません",
    ):
        service.create_snapshot(
            generated_at=CURRENT_TIME
        )


def test_service_rejects_quantity_mismatch(
    tmp_path: Path,
) -> None:
    """ローカルとBrokerの数量不一致を拒否する。"""

    repository = create_repository(tmp_path)
    create_local_position(repository, quantity=100)

    service = PortfolioService(
        position_repository=repository,
        broker=StaticBroker(
            positions=[
                create_broker_position(quantity=90)
            ],
            account=create_account(),
        ),
    )

    with pytest.raises(
        PortfolioConsistencyError,
        match="一致しません",
    ):
        service.create_snapshot(
            generated_at=CURRENT_TIME
        )


def test_service_rejects_missing_market_price(
    tmp_path: Path,
) -> None:
    """現在価格がなければ評価を拒否する。"""

    repository = create_repository(tmp_path)
    create_local_position(repository)

    service = PortfolioService(
        position_repository=repository,
        broker=StaticBroker(
            positions=[
                create_broker_position(
                    market_price=None
                )
            ],
            account=create_account(),
        ),
    )

    with pytest.raises(
        PortfolioPriceUnavailableError,
        match="現在価格",
    ):
        service.create_snapshot(
            generated_at=CURRENT_TIME
        )


def test_service_normalizes_generated_at_to_utc(
    tmp_path: Path,
) -> None:
    """集計日時をUTCへ正規化する。"""

    repository = create_repository(tmp_path)
    jst = timezone.utc

    service = PortfolioService(
        position_repository=repository,
        broker=StaticBroker(
            positions=[],
            account=create_account(
                cash_balance=1_000_000.0,
                buying_power=1_000_000.0,
                market_value=0.0,
                equity=1_000_000.0,
            ),
        ),
    )

    snapshot = service.create_snapshot(
        generated_at=CURRENT_TIME.astimezone(jst)
    )

    assert snapshot.generated_at == CURRENT_TIME


def test_service_rejects_naive_generated_at(
    tmp_path: Path,
) -> None:
    """タイムゾーンなし集計日時を拒否する。"""

    repository = create_repository(tmp_path)

    service = PortfolioService(
        position_repository=repository,
        broker=StaticBroker(
            positions=[],
            account=create_account(
                cash_balance=1_000_000.0,
                buying_power=1_000_000.0,
                market_value=0.0,
                equity=1_000_000.0,
            ),
        ),
    )

    with pytest.raises(ValueError, match="タイムゾーン"):
        service.create_snapshot(
            generated_at=datetime(
                2026,
                7,
                20,
                10,
                0,
            )
        )
