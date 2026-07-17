"""Broker接続状態と機能確認の共通モデル。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class BrokerHealthStatus(StrEnum):
    """Broker接続状態。"""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class BrokerCapabilityReport:
    """Broker Adapterが提供する機能一覧。"""

    broker_name: str
    submit_order: bool
    cancel_order: bool
    get_order: bool
    list_orders: bool
    list_positions: bool
    get_account: bool

    def __post_init__(self) -> None:
        """Broker名を検証する。"""

        normalized_name = self.broker_name.strip()

        if not normalized_name:
            raise ValueError(
                "Broker名を指定してください。"
            )

        object.__setattr__(
            self,
            "broker_name",
            normalized_name,
        )

    @property
    def is_complete(self) -> bool:
        """既存BrokerAdapterの全機能を備えるか返す。"""

        return all(
            (
                self.submit_order,
                self.cancel_order,
                self.get_order,
                self.list_orders,
                self.list_positions,
                self.get_account,
            )
        )


@dataclass(frozen=True, slots=True)
class BrokerHealthCheckResult:
    """Brokerへの読み取り系ヘルスチェック結果。"""

    broker_name: str
    checked_at: datetime
    status: BrokerHealthStatus
    account_accessible: bool
    orders_accessible: bool
    positions_accessible: bool
    active_order_count: int
    position_count: int
    error_messages: tuple[str, ...]

    def __post_init__(self) -> None:
        """状態・件数・日時を検証する。"""

        normalized_name = self.broker_name.strip()

        if not normalized_name:
            raise ValueError(
                "Broker名を指定してください。"
            )

        if self.checked_at.tzinfo is None:
            raise ValueError(
                "確認日時にはタイムゾーンが必要です。"
            )

        if self.active_order_count < 0:
            raise ValueError(
                "有効注文件数は0以上である必要があります。"
            )

        if self.position_count < 0:
            raise ValueError(
                "ポジション件数は0以上である必要があります。"
            )

        normalized_errors = tuple(
            message.strip()
            for message in self.error_messages
            if message.strip()
        )

        successful_count = sum(
            (
                self.account_accessible,
                self.orders_accessible,
                self.positions_accessible,
            )
        )

        expected_status = (
            BrokerHealthStatus.HEALTHY
            if successful_count == 3
            else (
                BrokerHealthStatus.UNAVAILABLE
                if successful_count == 0
                else BrokerHealthStatus.DEGRADED
            )
        )

        if self.status is not expected_status:
            raise ValueError(
                "接続状態と各確認結果が一致しません。"
            )

        if (
            self.status is BrokerHealthStatus.HEALTHY
            and normalized_errors
        ):
            raise ValueError(
                "正常結果にはエラーメッセージを"
                "設定できません。"
            )

        if (
            self.status is not BrokerHealthStatus.HEALTHY
            and not normalized_errors
        ):
            raise ValueError(
                "異常結果にはエラーメッセージが必要です。"
            )

        object.__setattr__(
            self,
            "broker_name",
            normalized_name,
        )
        object.__setattr__(
            self,
            "error_messages",
            normalized_errors,
        )

    @property
    def is_healthy(self) -> bool:
        """正常接続か返す。"""

        return self.status is BrokerHealthStatus.HEALTHY

    @property
    def is_degraded(self) -> bool:
        """一部機能のみ利用可能か返す。"""

        return self.status is BrokerHealthStatus.DEGRADED

    @property
    def is_unavailable(self) -> bool:
        """すべての確認に失敗したか返す。"""

        return self.status is BrokerHealthStatus.UNAVAILABLE
