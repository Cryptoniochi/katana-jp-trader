"""J-Quants APIから株価1分足を取得する。"""

import json
import os
from collections.abc import Callable
from datetime import datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.market.models import StockPrice

JQUANTS_BASE_URL = "https://api.jquants.com/v2"
MINUTE_BARS_ENDPOINT = "/equities/bars/minute"

JsonResponse = dict[str, object]
HttpGetter = Callable[[Request, float], JsonResponse]


class JQuantsDownloadError(RuntimeError):
    """J-Quants APIからの取得失敗を表す。"""


class JQuantsMinuteDownloader:
    """J-Quantsから1分足を取得してStockPriceへ変換する。"""

    def __init__(
        self,
        api_key: str | None = None,
        timeout_seconds: float = 30.0,
        http_getter: HttpGetter | None = None,
    ) -> None:
        """APIキー、タイムアウト、HTTP取得関数を設定する。"""

        resolved_api_key = (
            api_key if api_key is not None else os.getenv("JQUANTS_API_KEY", "")
        ).strip()

        if not resolved_api_key:
            raise ValueError(
                "J-Quants APIキーを指定するか、"
                "環境変数 JQUANTS_API_KEY を設定してください。"
            )

        if timeout_seconds <= 0:
            raise ValueError("タイムアウト秒数は0より大きい必要があります。")

        self.api_key = resolved_api_key
        self.timeout_seconds = timeout_seconds
        self.http_getter = http_getter or self._default_http_getter

    def download(
        self,
        code: str,
        date: str,
    ) -> list[StockPrice]:
        """指定銘柄・日付の1分足を全ページ取得する。"""

        normalized_code = self._normalize_request_code(code)
        normalized_date = self._normalize_request_date(date)

        rows: list[dict[str, object]] = []
        pagination_key: str | None = None

        while True:
            query_parameters = {
                "code": normalized_code,
                "date": normalized_date,
            }

            if pagination_key is not None:
                query_parameters["pagination_key"] = pagination_key

            response = self._request(query_parameters)

            page_rows = response.get("data", [])

            if not isinstance(page_rows, list):
                raise JQuantsDownloadError(
                    "J-Quantsレスポンスのdataが一覧形式ではありません。"
                )

            for row in page_rows:
                if not isinstance(row, dict):
                    raise JQuantsDownloadError(
                        "J-Quantsの分足データに不正な行が含まれています。"
                    )

                rows.append(row)

            raw_pagination_key = response.get("pagination_key")

            if not raw_pagination_key:
                break

            if not isinstance(raw_pagination_key, str):
                raise JQuantsDownloadError("pagination_keyが文字列ではありません。")

            pagination_key = raw_pagination_key

        prices = [self._convert_row(row) for row in rows]

        unique_prices = {(price.code, price.datetime): price for price in prices}

        return sorted(
            unique_prices.values(),
            key=lambda price: (
                price.datetime,
                price.code,
            ),
        )

    def _request(
        self,
        query_parameters: dict[str, str],
    ) -> JsonResponse:
        """J-Quants分足APIへ1回リクエストする。"""

        query = urlencode(query_parameters)

        request = Request(
            url=(f"{JQUANTS_BASE_URL}{MINUTE_BARS_ENDPOINT}?{query}"),
            method="GET",
            headers={
                "x-api-key": self.api_key,
                "Accept": "application/json",
                "User-Agent": "Project-KATANA/0.21.0",
            },
        )

        return self.http_getter(
            request,
            self.timeout_seconds,
        )

    @staticmethod
    def _default_http_getter(
        request: Request,
        timeout_seconds: float,
    ) -> JsonResponse:
        """標準ライブラリを使ってJSONを取得する。"""

        try:
            with urlopen(
                request,
                timeout=timeout_seconds,
            ) as response:
                response_text = response.read().decode("utf-8")

        except HTTPError as error:
            error_body = error.read().decode(
                "utf-8",
                errors="replace",
            )

            raise JQuantsDownloadError(
                "J-Quants APIがHTTPエラーを返しました。"
                f" status={error.code} body={error_body}"
            ) from error

        except URLError as error:
            raise JQuantsDownloadError(
                f"J-Quants APIへ接続できませんでした。 reason={error.reason}"
            ) from error

        try:
            parsed = json.loads(response_text)
        except json.JSONDecodeError as error:
            raise JQuantsDownloadError(
                "J-Quants APIから不正なJSONが返されました。"
            ) from error

        if not isinstance(parsed, dict):
            raise JQuantsDownloadError("J-Quants APIから想定外の形式が返されました。")

        return parsed

    @classmethod
    def _convert_row(
        cls,
        row: dict[str, object],
    ) -> StockPrice:
        """J-Quantsの1行をStockPriceへ変換する。"""

        required_fields = (
            "Date",
            "Time",
            "Code",
            "O",
            "H",
            "L",
            "C",
            "Vo",
        )

        missing_fields = [field for field in required_fields if field not in row]

        if missing_fields:
            raise JQuantsDownloadError(
                f"J-Quantsの分足データに必須項目がありません。 missing={missing_fields}"
            )

        try:
            traded_at = datetime.strptime(
                f"{row['Date']} {row['Time']}",
                "%Y-%m-%d %H:%M",
            )

            code = cls._normalize_response_code(str(row["Code"]))

            return StockPrice(
                code=code,
                datetime=traded_at,
                open=float(cls._require_number(row["O"], "O")),
                high=float(cls._require_number(row["H"], "H")),
                low=float(cls._require_number(row["L"], "L")),
                close=float(cls._require_number(row["C"], "C")),
                volume=int(
                    float(
                        cls._require_number(
                            row["Vo"],
                            "Vo",
                        )
                    )
                ),
            )

        except (TypeError, ValueError) as error:
            raise JQuantsDownloadError(
                f"J-Quantsの分足データをStockPriceへ変換できませんでした。 row={row}"
            ) from error

    @staticmethod
    def _require_number(
        value: Any,
        field_name: str,
    ) -> int | float:
        """数値項目がNoneでないことを確認する。"""

        if value is None:
            raise JQuantsDownloadError(f"{field_name}がnullです。")

        if not isinstance(
            value,
            int | float | str,
        ):
            raise JQuantsDownloadError(f"{field_name}が数値形式ではありません。")

        return value

    @staticmethod
    def _normalize_request_code(code: str) -> str:
        """APIリクエスト用の銘柄コードを検証する。"""

        normalized = code.strip()

        if not normalized.isdigit():
            raise ValueError("銘柄コードは数字で指定してください。")

        if len(normalized) not in (4, 5):
            raise ValueError("銘柄コードは4桁または5桁で指定してください。")

        return normalized

    @staticmethod
    def _normalize_response_code(code: str) -> str:
        """J-Quantsの5桁コードをKATANA用へ正規化する。"""

        normalized = code.strip()

        if len(normalized) == 5 and normalized.endswith("0"):
            return normalized[:4]

        return normalized

    @staticmethod
    def _normalize_request_date(date: str) -> str:
        """日付をYYYYMMDD形式へ正規化する。"""

        stripped = date.strip()

        supported_formats = (
            "%Y%m%d",
            "%Y-%m-%d",
        )

        for date_format in supported_formats:
            try:
                parsed = datetime.strptime(
                    stripped,
                    date_format,
                )
                return parsed.strftime("%Y%m%d")
            except ValueError:
                continue

        raise ValueError("日付はYYYYMMDDまたはYYYY-MM-DD形式で指定してください。")
