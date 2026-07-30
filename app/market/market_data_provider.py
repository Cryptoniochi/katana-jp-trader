"""市場データProviderの共通インターフェース。"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class MarketDataTick:
    """市場データProviderから受け取る1件のリアルタイム更新。"""

    code: str
    observed_at: datetime
    price: float
    cumulative_volume: float | None = None
    exchange: int = 1

    def __post_init__(self) -> None:
        """値を正規化して検証する。"""

        normalized_code = self.code.strip()

        if not normalized_code:
            raise ValueError("銘柄コードを指定してください。")

        if self.observed_at.tzinfo is None:
            raise ValueError(
                "観測日時にはタイムゾーンが必要です。"
            )

        if self.price <= 0:
            raise ValueError(
                "価格は0より大きい必要があります。"
            )

        if (
            self.cumulative_volume is not None
            and self.cumulative_volume < 0
        ):
            raise ValueError(
                "累積出来高は0以上である必要があります。"
            )

        if self.exchange <= 0:
            raise ValueError(
                "市場コードは0より大きい必要があります。"
            )

        object.__setattr__(self, "code", normalized_code)


@dataclass(frozen=True, slots=True)
class MarketDataProviderStatus:
    """市場データProviderの現在状態。"""

    provider_name: str
    is_connected: bool
    registered_codes: tuple[str, ...]
    last_message_at: datetime | None = None
    last_error: str | None = None

    def __post_init__(self) -> None:
        """状態値を検証する。"""

        if not self.provider_name.strip():
            raise ValueError(
                "Provider名を指定してください。"
            )

        if (
            self.last_message_at is not None
            and self.last_message_at.tzinfo is None
        ):
            raise ValueError(
                "最終受信日時にはタイムゾーンが必要です。"
            )


@runtime_checkable
class RealtimeMarketDataProvider(Protocol):
    """リアルタイム市場データProviderの共通契約。"""

    @property
    def provider_name(self) -> str:
        """Provider名を返す。"""

    def register_codes(
        self,
        codes: Iterable[str],
    ) -> tuple[str, ...]:
        """リアルタイム配信対象を登録する。"""

    def unregister_all(self) -> None:
        """リアルタイム配信対象をすべて解除する。"""

    def status(self) -> MarketDataProviderStatus:
        """現在状態を返す。"""
