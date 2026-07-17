"""既存BrokerAdapterの機能確認と接続診断を行う。"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Protocol

from app.broker.broker_health_models import (
    BrokerCapabilityReport,
    BrokerHealthCheckResult,
    BrokerHealthStatus,
)


class BrokerHealthReader(Protocol):
    """ヘルスチェックで利用するBroker読み取り機能。"""

    @property
    def broker_name(self) -> str:
        """Broker名を返す。"""

    def get_account(self):
        """口座情報を返す。"""

    def list_orders(
        self,
        *,
        active_only: bool = False,
    ):
        """注文一覧を返す。"""

    def list_positions(self):
        """ポジション一覧を返す。"""


class BrokerHealthService:
    """Broker Adapterを非発注処理だけで診断する。"""

    REQUIRED_METHODS = (
        "submit_order",
        "cancel_order",
        "get_order",
        "list_orders",
        "list_positions",
        "get_account",
    )

    def __init__(
        self,
        *,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        """診断用時計を設定する。"""

        self.now_provider = (
            now_provider
            if now_provider is not None
            else lambda: datetime.now(timezone.utc)
        )

    def inspect_capabilities(
        self,
        broker: object,
    ) -> BrokerCapabilityReport:
        """Brokerが実装する主要機能を確認する。"""

        broker_name = self._broker_name(broker)

        return BrokerCapabilityReport(
            broker_name=broker_name,
            submit_order=self._is_callable(
                broker,
                "submit_order",
            ),
            cancel_order=self._is_callable(
                broker,
                "cancel_order",
            ),
            get_order=self._is_callable(
                broker,
                "get_order",
            ),
            list_orders=self._is_callable(
                broker,
                "list_orders",
            ),
            list_positions=self._is_callable(
                broker,
                "list_positions",
            ),
            get_account=self._is_callable(
                broker,
                "get_account",
            ),
        )

    def check(
        self,
        broker: BrokerHealthReader,
    ) -> BrokerHealthCheckResult:
        """口座・注文・ポジション照会を安全に実行する。"""

        broker_name = self._broker_name(broker)
        checked_at = self._current_time()
        errors: list[str] = []

        account_accessible = False
        orders_accessible = False
        positions_accessible = False
        active_order_count = 0
        position_count = 0

        try:
            broker.get_account()
            account_accessible = True
        except Exception as error:
            errors.append(
                self._format_error(
                    "account",
                    error,
                )
            )

        try:
            orders = broker.list_orders(
                active_only=True
            )
            active_order_count = len(orders)
            orders_accessible = True
        except Exception as error:
            errors.append(
                self._format_error(
                    "orders",
                    error,
                )
            )

        try:
            positions = broker.list_positions()
            position_count = len(positions)
            positions_accessible = True
        except Exception as error:
            errors.append(
                self._format_error(
                    "positions",
                    error,
                )
            )

        successful_count = sum(
            (
                account_accessible,
                orders_accessible,
                positions_accessible,
            )
        )

        status = (
            BrokerHealthStatus.HEALTHY
            if successful_count == 3
            else (
                BrokerHealthStatus.UNAVAILABLE
                if successful_count == 0
                else BrokerHealthStatus.DEGRADED
            )
        )

        return BrokerHealthCheckResult(
            broker_name=broker_name,
            checked_at=checked_at,
            status=status,
            account_accessible=account_accessible,
            orders_accessible=orders_accessible,
            positions_accessible=positions_accessible,
            active_order_count=active_order_count,
            position_count=position_count,
            error_messages=tuple(errors),
        )

    def require_ready(
        self,
        broker: BrokerHealthReader,
    ) -> BrokerHealthCheckResult:
        """完全に利用可能でないBrokerを拒否する。"""

        capabilities = self.inspect_capabilities(
            broker
        )

        if not capabilities.is_complete:
            missing = [
                name
                for name in self.REQUIRED_METHODS
                if not getattr(
                    capabilities,
                    name,
                )
            ]
            raise RuntimeError(
                "Broker Adapterの必須機能が不足しています。 "
                f"missing={','.join(missing)}"
            )

        result = self.check(broker)

        if not result.is_healthy:
            raise RuntimeError(
                "Brokerのヘルスチェックに失敗しました。 "
                + " | ".join(result.error_messages)
            )

        return result

    def _current_time(self) -> datetime:
        """タイムゾーン付き現在日時をUTCへ正規化する。"""

        current = self.now_provider()

        if current.tzinfo is None:
            raise ValueError(
                "確認日時にはタイムゾーンが必要です。"
            )

        return current.astimezone(timezone.utc)

    @staticmethod
    def _broker_name(
        broker: object,
    ) -> str:
        """Broker名を検証して返す。"""

        raw_name = getattr(
            broker,
            "broker_name",
            "",
        )
        normalized = str(raw_name).strip()

        if not normalized:
            raise ValueError(
                "Broker名を取得できません。"
            )

        return normalized

    @staticmethod
    def _is_callable(
        broker: object,
        name: str,
    ) -> bool:
        """指定属性が呼び出し可能か返す。"""

        return callable(
            getattr(
                broker,
                name,
                None,
            )
        )

    @staticmethod
    def _format_error(
        target: str,
        error: Exception,
    ) -> str:
        """診断エラーを安定した文字列にする。"""

        detail = str(error).strip()
        error_name = type(error).__name__

        return (
            f"{target}: {error_name}"
            if not detail
            else f"{target}: {error_name}: {detail}"
        )
