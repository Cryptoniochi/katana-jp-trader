"""kabuステーションリアルタイム市場データサービス。"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable

from app.market.kabu_station_models import parse_push_tick
from app.market.kabu_station_realtime_provider import (
    KabuStationRealtimeProvider,
)
from app.market.kabu_station_websocket import (
    KabuStationWebSocketClient,
)
from app.market.market_data_provider import MarketDataTick
from app.market.realtime_bar_aggregator import (
    RealtimeBar,
    RealtimeBarAggregator,
)


LOGGER = logging.getLogger(__name__)


class KabuStationRealtimeService:
    """認証・銘柄登録・PUSH受信・5分足生成を統合する。"""

    def __init__(
        self,
        *,
        provider: KabuStationRealtimeProvider,
        websocket_client_factory: Callable[
            ..., KabuStationWebSocketClient
        ] = KabuStationWebSocketClient,
        on_tick: Callable[
            [MarketDataTick], None
        ] | None = None,
        on_completed_bar: Callable[
            [RealtimeBar], None
        ] | None = None,
        interval_minutes: int = 5,
    ) -> None:
        """各コンポーネントを構成する。"""

        self.provider = provider
        self.websocket_client_factory = (
            websocket_client_factory
        )
        self.on_tick = on_tick
        self.aggregator = RealtimeBarAggregator(
            interval_minutes=interval_minutes,
            on_completed_bar=on_completed_bar,
        )
        self._websocket_client: (
            KabuStationWebSocketClient | None
        ) = None
        self._registered_codes: tuple[str, ...] = ()

    @property
    def registered_codes(self) -> tuple[str, ...]:
        """現在の登録銘柄を返す。"""

        return self._registered_codes

    def start(
        self,
        codes: Iterable[str],
    ) -> tuple[str, ...]:
        """APIへ接続し、銘柄登録後にPUSH受信を開始する。"""

        normalized_codes = tuple(
            dict.fromkeys(
                code.strip()
                for code in codes
                if code.strip()
            )
        )
        if not normalized_codes:
            raise ValueError(
                "リアルタイム配信対象を指定してください。"
            )

        self.provider.connect()
        self._registered_codes = (
            self.provider.register_codes(
                normalized_codes
            )
        )

        websocket_client = (
            self.websocket_client_factory(
                on_message=self._on_push_message,
                on_state_change=self._on_state_change,
            )
        )
        self._websocket_client = websocket_client
        websocket_client.start()
        return self._registered_codes

    def update_registered_codes(
        self,
        codes: Iterable[str],
    ) -> tuple[str, ...]:
        """PUSH受信を継続したまま登録銘柄集合を更新する。"""

        normalized_codes = tuple(
            dict.fromkeys(
                code.strip()
                for code in codes
                if code.strip()
            )
        )
        if not normalized_codes:
            raise ValueError(
                "リアルタイム配信対象を指定してください。"
            )
        if normalized_codes == self._registered_codes:
            return self._registered_codes

        previous_codes = self._registered_codes
        try:
            self.provider.unregister_all()
            registered = self.provider.register_codes(
                normalized_codes
            )
        except Exception:
            if previous_codes:
                try:
                    self.provider.unregister_all()
                    self._registered_codes = (
                        self.provider.register_codes(previous_codes)
                    )
                except Exception:
                    LOGGER.exception(
                        "kabuステーション登録銘柄の"
                        "ロールバックに失敗しました。"
                    )
            raise

        self._registered_codes = registered
        return self._registered_codes

    def stop(self) -> tuple[RealtimeBar, ...]:
        """PUSH受信を停止し、途中バーを返す。"""

        websocket_client = self._websocket_client
        if websocket_client is not None:
            websocket_client.stop()
            self._websocket_client = None

        return self.aggregator.flush_all()

    def _on_push_message(
        self,
        payload: dict[str, object],
    ) -> None:
        """PUSHメッセージをTickへ変換して集計する。"""

        tick = parse_push_tick(payload)
        if tick is None:
            return

        self.provider.record_message_received(
            tick.observed_at
        )

        if self.on_tick is not None:
            self.on_tick(tick)

        self.aggregator.ingest(tick)

    def _on_state_change(
        self,
        state: str,
        detail: str | None,
    ) -> None:
        """WebSocket状態をProviderへ反映する。"""

        if state == "connected":
            LOGGER.info(
                "kabuステーションWebSocketへ接続しました。"
            )
            return

        if state in {
            "disconnected",
            "message_error",
        }:
            self.provider.record_disconnected(detail)

        if state == "reconnecting":
            LOGGER.warning(
                "kabuステーションWebSocketを"
                "再接続します。 %s",
                detail,
            )
