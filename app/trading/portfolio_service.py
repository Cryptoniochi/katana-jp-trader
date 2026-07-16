"""現在ポジションとBroker口座を集約する。"""

from datetime import datetime, timezone
from typing import Protocol

from app.trading.broker_adapter import (
    BrokerAccountSnapshot,
    BrokerPosition,
)
from app.trading.portfolio_models import (
    PortfolioPositionSnapshot,
    PortfolioSnapshot,
)
from app.trading.position_models import TradingPositionRecord


class PortfolioPositionReader(Protocol):
    """現在ポジション取得処理のインターフェース。"""

    def list_recent(
        self,
        *,
        limit: int = 100,
        code: str | None = None,
        side=None,
    ) -> list[TradingPositionRecord]:
        """現在ポジション一覧を返す。"""


class PortfolioBrokerReader(Protocol):
    """Broker口座・ポジション取得処理のインターフェース。"""

    def list_positions(self) -> list[BrokerPosition]:
        """Broker上の現在ポジション一覧を返す。"""

    def get_account(self) -> BrokerAccountSnapshot:
        """Broker口座情報を返す。"""


class PortfolioPriceUnavailableError(RuntimeError):
    """現在価格を取得できないことを表す。"""


class PortfolioConsistencyError(RuntimeError):
    """ローカルとBrokerのポジション不整合を表す。"""


class PortfolioService:
    """現在ポジションとBroker口座を集約する。"""

    def __init__(
        self,
        *,
        position_repository: PortfolioPositionReader,
        broker: PortfolioBrokerReader,
    ) -> None:
        """必要な依存関係を設定する。"""

        self.position_repository = position_repository
        self.broker = broker

    def create_snapshot(
        self,
        *,
        generated_at: datetime | None = None,
    ) -> PortfolioSnapshot:
        """現在のポートフォリオ評価を作成する。"""

        resolved_generated_at = (
            generated_at
            if generated_at is not None
            else datetime.now(timezone.utc)
        )

        if resolved_generated_at.tzinfo is None:
            raise ValueError(
                "集計日時にはタイムゾーンが必要です。"
            )

        account = self.broker.get_account()
        broker_positions = self.broker.list_positions()

        broker_position_map = {
            (
                position.code,
                position.side,
            ): position
            for position in broker_positions
        }

        local_positions = (
            self.position_repository.list_recent(
                limit=10_000,
            )
        )

        snapshots: list[
            PortfolioPositionSnapshot
        ] = []

        for record in local_positions:
            identity = (
                record.code,
                record.side,
            )
            broker_position = broker_position_map.get(
                identity
            )

            if broker_position is None:
                raise PortfolioConsistencyError(
                    "Broker側に対応するポジションが"
                    "存在しません。 "
                    f"code={record.code} "
                    f"side={record.side.value}"
                )

            if broker_position.quantity != record.quantity:
                raise PortfolioConsistencyError(
                    "ローカルとBrokerの保有数量が"
                    "一致しません。 "
                    f"code={record.code} "
                    f"local={record.quantity} "
                    f"broker={broker_position.quantity}"
                )

            if broker_position.market_price is None:
                raise PortfolioPriceUnavailableError(
                    "現在価格を取得できません。 "
                    f"code={record.code}"
                )

            snapshots.append(
                PortfolioPositionSnapshot(
                    position_id=record.position_id,
                    code=record.code,
                    side=record.side,
                    quantity=record.quantity,
                    average_cost=(
                        record.position.average_cost
                    ),
                    market_price=(
                        broker_position.market_price
                    ),
                    realized_profit_loss=(
                        record
                        .position
                        .realized_profit_loss
                    ),
                )
            )

        sorted_snapshots = tuple(
            sorted(
                snapshots,
                key=lambda item: (
                    item.code,
                    item.side.value,
                    item.position_id,
                ),
            )
        )

        return PortfolioSnapshot(
            currency=account.currency,
            cash_balance=account.cash_balance,
            buying_power=account.buying_power,
            broker_market_value=account.market_value,
            broker_equity=account.equity,
            positions=sorted_snapshots,
            generated_at=(
                resolved_generated_at.astimezone(
                    timezone.utc
                )
            ),
        )
