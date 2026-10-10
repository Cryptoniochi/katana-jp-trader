"""kabuステーションREST APIの低レベルClient。"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.market.kabu_station_models import (
    KabuStationConnectionError,
    KabuStationResponseError,
    KabuStationSymbol,
)


JsonObject = dict[str, Any]
JsonValue = JsonObject | list[JsonObject]
Transport = Callable[
    [str, str, dict[str, str], bytes | None, float],
    tuple[int, bytes],
]


@dataclass(frozen=True, slots=True)
class KabuStationClientSettings:
    """kabuステーションAPI接続設定。"""

    api_password: str
    base_url: str = "http://localhost:18080/kabusapi"
    timeout_seconds: float = 10.0
    maximum_registered_symbols: int = 50

    def __post_init__(self) -> None:
        """接続設定を検証する。"""

        if not self.api_password:
            raise ValueError(
                "kabuステーションAPIパスワードを"
                "指定してください。"
            )

        normalized_base_url = self.base_url.rstrip("/")

        if not normalized_base_url:
            raise ValueError(
                "APIのBase URLを指定してください。"
            )

        if self.timeout_seconds <= 0:
            raise ValueError(
                "タイムアウト秒数は0より大きい必要があります。"
            )

        if self.maximum_registered_symbols <= 0:
            raise ValueError(
                "最大登録銘柄数は0より大きい必要があります。"
            )

        object.__setattr__(
            self,
            "base_url",
            normalized_base_url,
        )


class KabuStationClient:
    """トークン取得とPUSH対象銘柄登録を担当する。"""

    def __init__(
        self,
        *,
        settings: KabuStationClientSettings,
        transport: Transport | None = None,
    ) -> None:
        """設定とHTTP Transportを保持する。"""

        self.settings = settings
        self.transport = transport or _urllib_transport
        self._token: str | None = None
        self._registered_symbols: tuple[
            KabuStationSymbol, ...
        ] = ()

    @property
    def token(self) -> str | None:
        """現在保持しているAPIトークンを返す。"""

        return self._token

    @property
    def registered_symbols(
        self,
    ) -> tuple[KabuStationSymbol, ...]:
        """Clientが最後に登録した銘柄を返す。"""

        return self._registered_symbols

    def issue_token(self) -> str:
        """APIパスワードから当日用トークンを取得する。"""

        response = self._request(
            "POST",
            "/token",
            payload={
                "APIPassword": self.settings.api_password
            },
            authenticated=False,
        )
        token = str(response.get("Token") or "").strip()

        if not token:
            raise KabuStationResponseError(
                "トークン応答にTokenがありません。"
            )

        self._token = token
        return token

    def register_symbols(
        self,
        symbols: Iterable[KabuStationSymbol],
    ) -> tuple[KabuStationSymbol, ...]:
        """PUSH配信対象銘柄を登録する。"""

        normalized = tuple(
            dict.fromkeys(symbols)
        )

        if not normalized:
            raise ValueError(
                "登録対象銘柄を1件以上指定してください。"
            )

        if (
            len(normalized)
            > self.settings.maximum_registered_symbols
        ):
            raise ValueError(
                "登録銘柄数が上限を超えています。 "
                f"count={len(normalized)} "
                "maximum="
                f"{self.settings.maximum_registered_symbols}"
            )

        self._ensure_token()
        self._request(
            "PUT",
            "/register",
            payload={
                "Symbols": [
                    symbol.to_payload()
                    for symbol in normalized
                ]
            },
        )
        self._registered_symbols = normalized
        return normalized

    def unregister_all(self) -> None:
        """PUSH配信対象銘柄をすべて解除する。"""

        self._ensure_token()
        self._request(
            "PUT",
            "/unregister/all",
            payload={},
        )
        self._registered_symbols = ()

    def board(
        self,
        symbol: KabuStationSymbol,
        *,
        timeout_seconds: float | None = None,
    ) -> JsonObject:
        """指定銘柄の現在値・板情報を取得する。

        timeout_secondsを指定した場合は、このBoard要求だけに適用する。
        token/register/unregisterや他のBoard要求の既定timeoutは変更しない。
        """

        self._ensure_token()
        return self._request(
            "GET",
            f"/board/{symbol.code}@{symbol.exchange}",
            payload=None,
            timeout_seconds=timeout_seconds,
        )

    def symbol_name(
        self,
        symbol: KabuStationSymbol,
    ) -> str | None:
        """板情報応答から銘柄名を取得する。"""

        payload = self.board(symbol)

        for key in (
            "SymbolName",
            "DisplayName",
            "SymbolNameFull",
        ):
            value = str(payload.get(key) or "").strip()

            if value:
                return value

        return None

    def cash_wallet(self) -> JsonObject:
        """現物取引余力を読取専用で取得する。"""

        self._ensure_token()
        return self._request("GET", "/wallet/cash", payload=None)

    def margin_wallet(self) -> JsonObject:
        """信用取引余力を読取専用で取得する。"""

        self._ensure_token()
        return self._request("GET", "/wallet/margin", payload=None)

    def orders(self, *, product: int = 0) -> tuple[JsonObject, ...]:
        """注文約定一覧を読取専用で取得する。"""

        if product not in {0, 1, 2, 3, 4}:
            raise ValueError("商品区分は0から4で指定してください。")
        self._ensure_token()
        value = self._request_value(
            "GET",
            f"/orders?product={product}",
            payload=None,
        )
        if not isinstance(value, list):
            raise KabuStationResponseError(
                "注文一覧応答はJSON Arrayである必要があります。"
            )
        return tuple(value)

    def send_order(self, payload: JsonObject) -> JsonObject:
        """現物・信用の注文を発注し、kabuステーション応答を返す。

        この低レベルClientは注文内容の業務ルールを解釈しない。
        呼び出し側で公式API仕様に適合するpayloadを構築すること。
        """

        if not isinstance(payload, dict) or not payload:
            raise ValueError("発注payloadを指定してください。")

        self._ensure_token()
        response = self._request(
            "POST",
            "/sendorder",
            payload=payload,
        )

        result = response.get("Result")
        order_id = str(response.get("OrderId") or "").strip()
        if result != 0 or not order_id:
            raise KabuStationResponseError(
                "発注応答が成功形式ではありません。 "
                f"result={result} order_id={order_id!r}"
            )

        return response

    def positions(
        self,
        *,
        product: int = 0,
        addinfo: bool = True,
    ) -> tuple[JsonObject, ...]:
        """残高一覧を読取専用で取得する。"""

        if product not in {0, 1, 2, 3, 4}:
            raise ValueError("商品区分は0から4で指定してください。")
        flag = "true" if addinfo else "false"
        self._ensure_token()
        value = self._request_value(
            "GET",
            f"/positions?product={product}&addinfo={flag}",
            payload=None,
        )
        if not isinstance(value, list):
            raise KabuStationResponseError(
                "残高一覧応答はJSON Arrayである必要があります。"
            )
        return tuple(value)

    def _ensure_token(self) -> str:
        """トークン未取得の場合は自動取得する。"""

        if self._token is None:
            return self.issue_token()

        return self._token

    def _request(
        self,
        method: str,
        path: str,
        *,
        payload: JsonObject | None,
        authenticated: bool = True,
        timeout_seconds: float | None = None,
    ) -> JsonObject:
        """JSON APIを呼び出して応答を検証する。"""

        resolved_timeout_seconds = (
            self.settings.timeout_seconds
            if timeout_seconds is None
            else float(timeout_seconds)
        )
        if resolved_timeout_seconds <= 0:
            raise ValueError(
                "要求タイムアウト秒数は0より大きい必要があります。"
            )

        headers = {
            "Content-Type": "application/json",
        }

        if authenticated:
            token = self._token

            if token is None:
                raise RuntimeError(
                    "認証済み要求にはトークンが必要です。"
                )

            headers["X-API-KEY"] = token

        body = (
            None
            if payload is None
            else json.dumps(payload).encode("utf-8")
        )
        url = f"{self.settings.base_url}{path}"

        try:
            status, response_body = self.transport(
                method,
                url,
                headers,
                body,
                resolved_timeout_seconds,
            )
        except KabuStationConnectionError:
            raise
        except Exception as error:
            raise KabuStationConnectionError(
                "kabuステーションAPIへの接続に"
                "失敗しました。 "
                f"url={url} error={error}"
            ) from error

        response = self._validate_response(
            status,
            response_body,
        )

        if not isinstance(response, dict):
            raise KabuStationResponseError(
                "kabuステーションAPI応答は"
                "JSON Objectである必要があります。"
            )

        return response

    def _request_value(
        self,
        method: str,
        path: str,
        *,
        payload: JsonObject | None,
        authenticated: bool = True,
        timeout_seconds: float | None = None,
    ) -> JsonValue:
        """ObjectまたはArrayのJSON APIを呼び出す。"""

        resolved_timeout_seconds = (
            self.settings.timeout_seconds
            if timeout_seconds is None
            else float(timeout_seconds)
        )
        if resolved_timeout_seconds <= 0:
            raise ValueError(
                "要求タイムアウト秒数は0より大きい必要があります。"
            )

        headers = {"Content-Type": "application/json"}
        if authenticated:
            token = self._token
            if token is None:
                raise RuntimeError(
                    "認証済み要求にはトークンが必要です。"
                )
            headers["X-API-KEY"] = token

        body = (
            None
            if payload is None
            else json.dumps(payload).encode("utf-8")
        )
        url = f"{self.settings.base_url}{path}"
        try:
            status, response_body = self.transport(
                method,
                url,
                headers,
                body,
                resolved_timeout_seconds,
            )
        except KabuStationConnectionError:
            raise
        except Exception as error:
            raise KabuStationConnectionError(
                "kabuステーションAPIへの接続に"
                "失敗しました。 "
                f"url={url} error={error}"
            ) from error

        return self._validate_response(status, response_body)

    @staticmethod
    def _validate_response(
        status: int,
        response_body: bytes,
    ) -> JsonValue:
        response = _decode_json_value(response_body)

        if not 200 <= status < 300:
            error_payload = (
                response if isinstance(response, dict) else {}
            )
            code = error_payload.get("Code")
            message = error_payload.get("Message")
            raise KabuStationResponseError(
                "kabuステーションAPIがエラーを"
                "返しました。 "
                f"status={status} "
                f"code={code} message={message}"
            )

        return response


def _decode_json(body: bytes) -> JsonObject:
    """空応答を含むJSON Bodyを辞書へ変換する。"""

    if not body:
        return {}

    value = _decode_json_value(body)

    if not isinstance(value, dict):
        raise KabuStationResponseError(
            "kabuステーションAPI応答は"
            "JSON Objectである必要があります。"
        )

    return value


def _decode_json_value(body: bytes) -> JsonValue:
    """ObjectまたはObject配列のJSON Bodyを解釈する。"""

    if not body:
        return {}
    try:
        value = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise KabuStationResponseError(
            "kabuステーションAPI応答をJSONとして"
            "解釈できません。"
        ) from error

    if isinstance(value, dict):
        return value
    if isinstance(value, list) and all(
        isinstance(item, dict) for item in value
    ):
        return value
    raise KabuStationResponseError(
        "kabuステーションAPI応答はJSON Objectまたは"
        "Object配列である必要があります。"
    )


def _urllib_transport(
    method: str,
    url: str,
    headers: dict[str, str],
    body: bytes | None,
    timeout_seconds: float,
) -> tuple[int, bytes]:
    """標準ライブラリでHTTP要求を送信する。"""

    request = Request(
        url=url,
        data=body,
        headers=headers,
        method=method,
    )

    try:
        with urlopen(
            request,
            timeout=timeout_seconds,
        ) as response:
            return response.status, response.read()
    except HTTPError as error:
        return error.code, error.read()
    except URLError as error:
        raise KabuStationConnectionError(
            "kabuステーションAPIへ接続できません。 "
            f"reason={error.reason}"
        ) from error
