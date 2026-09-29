"""Paper・Shadow・Liveの実行モードとLive解除条件を管理する。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Protocol

from app.trading.broker_adapter import BrokerAdapter


class TradingExecutionMode(StrEnum):
    """KATANAが使用する注文実行モード。"""

    PAPER = "paper"
    SHADOW = "shadow"
    LIVE = "live"


class LiveTradingLockError(RuntimeError):
    """Live実行の解除条件を満たしていない。"""


class LiveTradingUnavailableError(RuntimeError):
    """Live注文送信機能がまだ導入されていない。"""


@dataclass(frozen=True, slots=True)
class ExecutionModeSettings:
    """環境変数から読み取る安全側の実行モード設定。"""

    mode: TradingExecutionMode = TradingExecutionMode.PAPER
    live_armed: bool = False
    live_confirmation: str | None = None

    @classmethod
    def from_environment(
        cls,
        environment: Mapping[str, str],
    ) -> "ExecutionModeSettings":
        """明示されない限りPaperとなる設定を構築する。"""

        raw_mode = environment.get(
            "KATANA_EXECUTION_MODE",
            TradingExecutionMode.PAPER.value,
        )

        try:
            mode = TradingExecutionMode(
                raw_mode.strip().lower()
            )
        except ValueError as error:
            raise ValueError(
                "KATANA_EXECUTION_MODEは"
                "paper、shadow、liveのいずれかで"
                "指定してください。"
            ) from error

        live_armed = (
            environment.get(
                "KATANA_LIVE_TRADING_ARMED",
                "",
            )
            .strip()
            .upper()
            == "YES"
        )
        confirmation = environment.get(
            "KATANA_LIVE_TRADING_CONFIRMATION"
        )
        normalized_confirmation = (
            confirmation.strip()
            if confirmation is not None
            and confirmation.strip()
            else None
        )

        return cls(
            mode=mode,
            live_armed=live_armed,
            live_confirmation=normalized_confirmation,
        )


@dataclass(frozen=True, slots=True)
class LiveArmingPolicy:
    """Live実行に日次二重解除を要求する。"""

    confirmation_prefix: str = "KATANA-LIVE"

    def __post_init__(self) -> None:
        normalized = self.confirmation_prefix.strip().upper()

        if not normalized:
            raise ValueError(
                "Live確認プレフィックスを指定してください。"
            )

        object.__setattr__(
            self,
            "confirmation_prefix",
            normalized,
        )

    def expected_confirmation(
        self,
        trading_date: date,
    ) -> str:
        """指定日の確認文字列を返す。"""

        return (
            f"{self.confirmation_prefix}-"
            f"{trading_date.isoformat()}"
        )

    def require_authorized(
        self,
        settings: ExecutionModeSettings,
        *,
        trading_date: date,
    ) -> None:
        """Live実行の二重解除を検証する。"""

        if settings.mode is not TradingExecutionMode.LIVE:
            raise LiveTradingLockError(
                "実行モードがliveではありません。"
            )

        if not settings.live_armed:
            raise LiveTradingLockError(
                "KATANA_LIVE_TRADING_ARMED=YESが必要です。"
            )

        expected = self.expected_confirmation(
            trading_date
        )

        if settings.live_confirmation != expected:
            raise LiveTradingLockError(
                "当日のLive確認文字列が一致しません。"
            )


class BrokerProvider(Protocol):
    """実行モードに対応するBrokerを提供する。"""

    @property
    def paper_broker(self) -> BrokerAdapter:
        """Paper Brokerを返す。"""

    @property
    def shadow_broker(self) -> BrokerAdapter:
        """Shadow Brokerを返す。"""


@dataclass(frozen=True, slots=True)
class ExecutionModeRouter:
    """Liveを実装不能に保った第1段階のBroker選択器。"""

    paper_broker: BrokerAdapter
    shadow_broker: BrokerAdapter
    arming_policy: LiveArmingPolicy = LiveArmingPolicy()

    def resolve(
        self,
        settings: ExecutionModeSettings,
        *,
        trading_date: date,
    ) -> BrokerAdapter:
        """PaperまたはShadowを返し、Live送信は必ず拒否する。"""

        if settings.mode is TradingExecutionMode.PAPER:
            return self.paper_broker

        if settings.mode is TradingExecutionMode.SHADOW:
            return self.shadow_broker

        self.arming_policy.require_authorized(
            settings,
            trading_date=trading_date,
        )

        raise LiveTradingUnavailableError(
            "Live注文送信Adapterは未導入です。"
            "現在はShadowモードまで利用できます。"
        )
