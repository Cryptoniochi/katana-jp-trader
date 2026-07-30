"""kabuステーションAPI用リアルタイムProvider。"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone

from app.market.kabu_station_client import KabuStationClient
from app.market.kabu_station_models import KabuStationSymbol
from app.market.market_data_provider import (
    MarketDataProviderStatus,
)


class KabuStationRealtimeProvider:
    """認証・銘柄登録・接続診断を管理するProvider。"""

    def __init__(
        self,
        *,
        client: KabuStationClient,
        exchange: int = 1,
    ) -> None:
        """Clientと既定市場コードを保持する。"""

        if exchange <= 0:
            raise ValueError(
                "市場コードは0より大きい必要があります。"
            )

        self.client = client
        self.exchange = exchange
        self._is_connected = False
        self._last_message_at: datetime | None = None
        self._last_error: str | None = None

    @property
    def provider_name(self) -> str:
        """Provider名を返す。"""

        return "kabu-station"

    def connect(self) -> str:
        """APIトークンを取得して利用可能状態にする。"""

        try:
            token = self.client.issue_token()
        except Exception as error:
            self._is_connected = False
            self._last_error = str(error)
            raise

        self._is_connected = True
        self._last_error = None
        return token

    def reconnect_and_register(
        self,
        codes: Iterable[str],
    ) -> tuple[str, ...]:
        """トークン再取得後に銘柄を再登録する。"""

        self.connect()
        return self.register_codes(codes)

    def register_codes(
        self,
        codes: Iterable[str],
    ) -> tuple[str, ...]:
        """指定銘柄をPUSH配信対象へ登録する。"""

        symbols = tuple(
            dict.fromkeys(
                KabuStationSymbol(
                    code=code,
                    exchange=self.exchange,
                )
                for code in codes
            )
        )

        try:
            registered = self.client.register_symbols(
                symbols
            )
        except Exception as error:
            self._last_error = str(error)
            raise

        self._is_connected = True
        self._last_error = None
        return tuple(
            symbol.code
            for symbol in registered
        )

    def unregister_all(self) -> None:
        """登録銘柄をすべて解除する。"""

        try:
            self.client.unregister_all()
        except Exception as error:
            self._last_error = str(error)
            raise

        self._last_error = None

    def record_message_received(
        self,
        observed_at: datetime | None = None,
    ) -> None:
        """WebSocket受信時刻を状態へ記録する。"""

        resolved = (
            observed_at
            if observed_at is not None
            else datetime.now(timezone.utc)
        )

        if resolved.tzinfo is None:
            raise ValueError(
                "受信日時にはタイムゾーンが必要です。"
            )

        self._last_message_at = resolved
        self._is_connected = True
        self._last_error = None

    def record_disconnected(
        self,
        error_message: str | None = None,
    ) -> None:
        """切断状態と原因を記録する。"""

        self._is_connected = False
        self._last_error = (
            error_message.strip()
            if error_message
            and error_message.strip()
            else None
        )

    def status(self) -> MarketDataProviderStatus:
        """現在状態を返す。"""

        return MarketDataProviderStatus(
            provider_name=self.provider_name,
            is_connected=self._is_connected,
            registered_codes=tuple(
                symbol.code
                for symbol
                in self.client.registered_symbols
            ),
            last_message_at=self._last_message_at,
            last_error=self._last_error,
        )
