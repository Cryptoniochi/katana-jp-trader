"""kabuステーションAPI WebSocket受信クライアント。"""

from __future__ import annotations

import json
import logging
import random
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from app.market.kabu_station_models import (
    KabuStationConnectionError,
)


LOGGER = logging.getLogger(__name__)

JsonObject = dict[str, Any]
MessageHandler = Callable[[JsonObject], None]
StateHandler = Callable[[str, str | None], None]


class WebSocketAppProtocol(Protocol):
    """websocket-client WebSocketAppの最小契約。"""

    def run_forever(self, **kwargs: Any) -> bool:
        """接続を開始し、切断まで待機する。"""

    def close(self) -> None:
        """接続を閉じる。"""


WebSocketFactory = Callable[..., WebSocketAppProtocol]


@dataclass(frozen=True, slots=True)
class ReconnectPolicy:
    """WebSocket再接続ポリシー。"""

    initial_delay_seconds: float = 1.0
    maximum_delay_seconds: float = 30.0
    multiplier: float = 2.0
    jitter_ratio: float = 0.2

    def __post_init__(self) -> None:
        """設定値を検証する。"""

        if self.initial_delay_seconds <= 0:
            raise ValueError(
                "初回再接続待機秒数は0より大きい必要があります。"
            )
        if self.maximum_delay_seconds <= 0:
            raise ValueError(
                "最大再接続待機秒数は0より大きい必要があります。"
            )
        if self.maximum_delay_seconds < self.initial_delay_seconds:
            raise ValueError(
                "最大再接続待機秒数は初回待機秒数以上が必要です。"
            )
        if self.multiplier < 1:
            raise ValueError(
                "再接続倍率は1以上が必要です。"
            )
        if not 0 <= self.jitter_ratio <= 1:
            raise ValueError(
                "ジッター比率は0以上1以下が必要です。"
            )

    def delay_for_attempt(self, attempt: int) -> float:
        """再接続回数に応じた待機秒数を返す。"""

        if attempt < 0:
            raise ValueError(
                "再接続回数は0以上である必要があります。"
            )

        base_delay = min(
            self.maximum_delay_seconds,
            self.initial_delay_seconds
            * (self.multiplier ** attempt),
        )
        jitter_width = base_delay * self.jitter_ratio
        return max(
            0.0,
            random.uniform(
                base_delay - jitter_width,
                base_delay + jitter_width,
            ),
        )


class KabuStationWebSocketClient:
    """kabuステーションPUSH配信を受信する。"""

    def __init__(
        self,
        *,
        url: str = (
            "ws://localhost:18080/kabusapi/websocket"
        ),
        on_message: MessageHandler,
        on_state_change: StateHandler | None = None,
        websocket_factory: WebSocketFactory | None = None,
        reconnect_policy: ReconnectPolicy | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        """受信ハンドラーと再接続設定を保持する。"""

        if not url.strip():
            raise ValueError(
                "WebSocket URLを指定してください。"
            )

        self.url = url.strip()
        self.on_message = on_message
        self.on_state_change = on_state_change
        self.websocket_factory = (
            websocket_factory
            or _default_websocket_factory
        )
        self.reconnect_policy = (
            reconnect_policy or ReconnectPolicy()
        )
        self.sleep = sleep

        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._current_app: WebSocketAppProtocol | None = None
        self._lock = threading.Lock()

    @property
    def is_running(self) -> bool:
        """受信スレッドが動作中か返す。"""

        thread = self._thread
        return (
            thread is not None
            and thread.is_alive()
            and not self._stop_event.is_set()
        )

    def start(self) -> None:
        """バックグラウンドで受信を開始する。"""

        with self._lock:
            if self.is_running:
                return

            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self.run,
                name="kabu-station-websocket",
                daemon=True,
            )
            self._thread.start()

    def run(self) -> None:
        """停止要求まで接続と再接続を繰り返す。"""

        attempt = 0

        while not self._stop_event.is_set():
            self._emit_state("connecting", None)

            app = self.websocket_factory(
                self.url,
                on_open=self._handle_open,
                on_message=self._handle_message,
                on_error=self._handle_error,
                on_close=self._handle_close,
            )
            self._current_app = app

            try:
                app.run_forever()
            except Exception as error:
                LOGGER.exception(
                    "kabuステーションWebSocketで"
                    "未処理例外が発生しました。"
                )
                self._emit_state(
                    "disconnected",
                    str(error),
                )
            finally:
                self._current_app = None

            if self._stop_event.is_set():
                break

            delay = self.reconnect_policy.delay_for_attempt(
                attempt
            )
            self._emit_state(
                "reconnecting",
                f"retry_after={delay:.2f}",
            )
            self.sleep(delay)
            attempt += 1

        self._emit_state("stopped", None)

    def stop(self, join_timeout_seconds: float = 5.0) -> None:
        """受信を停止する。"""

        self._stop_event.set()

        app = self._current_app
        if app is not None:
            try:
                app.close()
            except Exception:
                LOGGER.exception(
                    "WebSocketのcloseに失敗しました。"
                )

        thread = self._thread
        if (
            thread is not None
            and thread is not threading.current_thread()
        ):
            thread.join(timeout=join_timeout_seconds)

    def _handle_open(self, _app: Any) -> None:
        """接続成功状態を通知する。"""

        self._emit_state("connected", None)

    def _handle_message(
        self,
        _app: Any,
        message: str | bytes,
    ) -> None:
        """JSONメッセージを辞書へ変換して通知する。"""

        try:
            if isinstance(message, bytes):
                message = message.decode("utf-8")

            payload = json.loads(message)
        except (
            UnicodeDecodeError,
            json.JSONDecodeError,
        ) as error:
            LOGGER.warning(
                "PUSHメッセージをJSONとして"
                "解釈できません: %s",
                error,
            )
            self._emit_state(
                "message_error",
                str(error),
            )
            return

        if not isinstance(payload, dict):
            self._emit_state(
                "message_error",
                "PUSHメッセージがJSON Objectではありません。",
            )
            return

        self.on_message(payload)

    def _handle_error(
        self,
        _app: Any,
        error: object,
    ) -> None:
        """WebSocketエラーを状態へ通知する。"""

        self._emit_state(
            "disconnected",
            str(error),
        )

    def _handle_close(
        self,
        _app: Any,
        status_code: int | None,
        message: str | None,
    ) -> None:
        """切断状態を通知する。"""

        detail = (
            None
            if status_code is None and not message
            else (
                f"status_code={status_code} "
                f"message={message}"
            )
        )
        self._emit_state("disconnected", detail)

    def _emit_state(
        self,
        state: str,
        detail: str | None,
    ) -> None:
        """状態変更ハンドラーを安全に呼び出す。"""

        handler = self.on_state_change
        if handler is None:
            return

        try:
            handler(state, detail)
        except Exception:
            LOGGER.exception(
                "WebSocket状態変更ハンドラーで"
                "例外が発生しました。"
            )


def _default_websocket_factory(
    url: str,
    **callbacks: Any,
) -> WebSocketAppProtocol:
    """websocket-clientのWebSocketAppを生成する。"""

    try:
        import websocket
    except ImportError as error:
        raise KabuStationConnectionError(
            "WebSocket受信にはwebsocket-clientが必要です。"
            " `python -m pip install websocket-client` "
            "を実行してください。"
        ) from error

    return websocket.WebSocketApp(
        url,
        **callbacks,
    )
