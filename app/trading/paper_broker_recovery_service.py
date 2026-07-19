"""SQLite永続状態からPaper Brokerを復元するService。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.trading.broker_adapter import (
    BrokerOrderSnapshot,
    BrokerPosition,
)
from app.trading.order_models import TradeOrderRecord
from app.trading.paper_broker import PaperBroker
from app.trading.paper_broker_state import (
    PaperBrokerRestoredOrder,
    PaperBrokerState,
)
from app.trading.portfolio_models import PortfolioSnapshot
from app.trading.position_models import TradingPositionRecord


class PaperBrokerRecoveryError(RuntimeError):
    """Paper Broker状態復元に失敗したことを表す。"""


class RecoveryOrderRepository(Protocol):
    """復元処理が利用する注文Repositoryの最小契約。"""

    def list_recent(
        self,
        *,
        limit: int = 100,
        code=None,
        status=None,
        side=None,
    ) -> list[TradeOrderRecord]:
        """保存済み注文を新しい順に返す。"""


class RecoveryPositionRepository(Protocol):
    """復元処理が利用するポジションRepositoryの最小契約。"""

    def list_recent(
        self,
        *,
        limit: int = 100,
        code=None,
        side=None,
    ) -> list[TradingPositionRecord]:
        """現在ポジションを新しい順に返す。"""


class RecoveryPortfolioRepository(Protocol):
    """復元処理が利用するPortfolio Repositoryの最小契約。"""

    def latest(
        self,
    ) -> PortfolioSnapshot | None:
        """最新のPortfolio Snapshotを返す。"""


@dataclass(frozen=True, slots=True)
class PaperBrokerRecoveryResult:
    """Paper Broker復元結果。"""

    restored: bool
    used_portfolio_snapshot: bool
    cash_balance: float
    position_count: int
    order_count: int
    market_price_count: int

    @property
    def is_empty(
        self,
    ) -> bool:
        """資金以外の復元対象がなかったか返す。"""

        return (
            self.position_count == 0
            and self.order_count == 0
            and self.market_price_count == 0
        )


class PaperBrokerRecoveryService:
    """永続化済み注文・ポジション・PortfolioからBrokerを復元する。"""

    def __init__(
        self,
        *,
        broker: PaperBroker,
        order_repository: RecoveryOrderRepository,
        position_repository: RecoveryPositionRepository,
        portfolio_repository: RecoveryPortfolioRepository,
        order_limit: int = 10_000,
        position_limit: int = 10_000,
    ) -> None:
        """Broker・Repository・最大取得件数を設定する。"""

        if order_limit <= 0:
            raise ValueError(
                "注文取得件数は0より大きい必要があります。"
            )

        if position_limit <= 0:
            raise ValueError(
                "ポジション取得件数は0より大きい必要があります。"
            )

        self.broker = broker
        self.order_repository = order_repository
        self.position_repository = position_repository
        self.portfolio_repository = portfolio_repository
        self.order_limit = order_limit
        self.position_limit = position_limit

    def recover(
        self,
    ) -> PaperBrokerRecoveryResult:
        """永続状態を読み込み、Paper Brokerへ一括反映する。"""

        try:
            state, used_portfolio_snapshot = self.build_state()

            self.broker.restore_state(
                cash_balance=state.cash_balance,
                positions=state.position_list(),
                orders=state.order_pairs(),
                market_prices=state.market_price_dict(),
            )

        except PaperBrokerRecoveryError:
            raise
        except Exception as error:
            raise PaperBrokerRecoveryError(
                "Paper Brokerの状態を復元できませんでした。"
            ) from error

        return PaperBrokerRecoveryResult(
            restored=True,
            used_portfolio_snapshot=used_portfolio_snapshot,
            cash_balance=state.cash_balance,
            position_count=len(state.positions),
            order_count=len(state.orders),
            market_price_count=len(state.market_prices),
        )

    def build_state(
        self,
    ) -> tuple[PaperBrokerState, bool]:
        """Repository群から復元用状態を構築する。"""

        try:
            latest_portfolio = self.portfolio_repository.latest()
            position_records = self.position_repository.list_recent(
                limit=self.position_limit,
            )
            order_records = self.order_repository.list_recent(
                limit=self.order_limit,
            )
        except Exception as error:
            raise PaperBrokerRecoveryError(
                "Paper Broker復元用データを"
                "Repositoryから読み込めませんでした。"
            ) from error

        cash_balance = (
            latest_portfolio.cash_balance
            if latest_portfolio is not None
            else self.broker.settings.initial_cash
        )

        market_prices = self._create_market_prices(
            latest_portfolio=latest_portfolio,
        )
        positions = self._create_positions(
            records=position_records,
            market_prices=market_prices,
        )
        restored_orders = self._create_orders(
            records=order_records,
        )

        return (
            PaperBrokerState(
                cash_balance=cash_balance,
                positions=tuple(positions),
                orders=tuple(restored_orders),
                market_prices=market_prices,
            ),
            latest_portfolio is not None,
        )

    @staticmethod
    def _create_market_prices(
        *,
        latest_portfolio: PortfolioSnapshot | None,
    ) -> dict[str, float]:
        """最新Portfolioから銘柄別現在価格を作成する。"""

        if latest_portfolio is None:
            return {}

        market_prices: dict[str, float] = {}

        for position in latest_portfolio.positions:
            existing = market_prices.get(
                position.code,
            )

            if (
                existing is not None
                and existing != position.market_price
            ):
                raise PaperBrokerRecoveryError(
                    "最新Portfolio内で同一銘柄の現在価格が"
                    "一致しません。 "
                    f"code={position.code} "
                    f"first={existing} "
                    f"second={position.market_price}"
                )

            market_prices[
                position.code
            ] = position.market_price

        return market_prices

    @staticmethod
    def _create_positions(
        *,
        records: list[TradingPositionRecord],
        market_prices: dict[str, float],
    ) -> list[BrokerPosition]:
        """現在ポジションRecordをBroker Positionへ変換する。"""

        positions: list[BrokerPosition] = []
        identities: set[tuple[str, object]] = set()

        for record in records:
            position = record.position
            identity = (
                position.code,
                position.side,
            )

            if identity in identities:
                raise PaperBrokerRecoveryError(
                    "復元対象ポジションの銘柄・方向が"
                    "重複しています。 "
                    f"code={position.code} "
                    f"side={position.side.value}"
                )

            identities.add(identity)

            market_price = market_prices.get(
                position.code,
                position.average_cost,
            )
            market_prices.setdefault(
                position.code,
                market_price,
            )

            positions.append(
                BrokerPosition(
                    code=position.code,
                    side=position.side,
                    quantity=position.quantity,
                    average_price=position.average_cost,
                    market_price=market_price,
                    updated_at=record.updated_at,
                )
            )

        return positions

    @staticmethod
    def _create_orders(
        *,
        records: list[TradeOrderRecord],
    ) -> list[PaperBrokerRestoredOrder]:
        """Brokerへ送信済みの注文Recordを復元注文へ変換する。"""

        restored_orders: list[
            PaperBrokerRestoredOrder
        ] = []

        for record in records:
            if record.broker_order_id is None:
                continue

            submitted_at = (
                record.submitted_at
                if record.submitted_at is not None
                else record.created_at
            )

            snapshot = BrokerOrderSnapshot(
                broker_order_id=record.broker_order_id,
                client_order_id=record.order.order_id,
                code=record.order.code,
                side=record.order.side,
                status=record.status,
                quantity=record.order.quantity,
                filled_quantity=record.filled_quantity,
                average_fill_price=record.average_fill_price,
                submitted_at=submitted_at,
                updated_at=record.updated_at,
                status_reason=record.status_reason,
            )

            restored_orders.append(
                PaperBrokerRestoredOrder(
                    order=record.order,
                    snapshot=snapshot,
                )
            )

        return restored_orders
