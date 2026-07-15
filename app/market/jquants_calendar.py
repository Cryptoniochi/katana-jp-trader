"""J-Quants APIから東証の取引カレンダーを取得する。"""

import json
import os
from collections.abc import Callable
from datetime import date, datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

JQUANTS_BASE_URL = "https://api.jquants.com/v2"
TRADING_CALENDAR_ENDPOINT = "/markets/calendar"

JsonResponse = dict[str, object]
HttpGetter = Callable[[Request, float], JsonResponse]


class JQuantsCalendarError(RuntimeError):
    """J-Quants取引カレンダーの取得失敗を表す。"""


class JQuantsTradingCalendarClient:
    """J-Quantsから東証の営業日一覧を取得する。"""

    BUSINESS_HOLIDAY_DIVISIONS = frozenset(
        {
            "1",
            "2",
        }
    )

    def __init__(
        self,
        api_key: str | None = None,
        timeout_seconds: float = 30.0,
        http_getter: HttpGetter | None = None,
    ) -> None:
        """APIキーとHTTP取得処理を設定する。"""

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

    def get_business_dates(
        self,
        start_date: date,
        end_date: date,
    ) -> list[date]:
        """指定期間内の東証営業日を返す。"""

        if start_date > end_date:
            raise ValueError("開始日は終了日以前にしてください。")

        response = self._request(
            start_date=start_date,
            end_date=end_date,
        )

        raw_rows = response.get("data", [])

        if not isinstance(raw_rows, list):
            raise JQuantsCalendarError("取引カレンダーのdataが一覧形式ではありません。")

        business_dates: list[date] = []

        for raw_row in raw_rows:
            if not isinstance(raw_row, dict):
                raise JQuantsCalendarError("取引カレンダーに不正な行が含まれています。")

            raw_date = raw_row.get("Date")
            holiday_division = raw_row.get("HolDiv")

            if raw_date is None or holiday_division is None:
                raise JQuantsCalendarError(
                    "取引カレンダーにDateまたはHolDivがありません。"
                )

            try:
                calendar_date = datetime.strptime(
                    str(raw_date),
                    "%Y-%m-%d",
                ).date()
            except ValueError as error:
                raise JQuantsCalendarError(
                    "取引カレンダーの日付形式が不正です。"
                ) from error

            if str(holiday_division) in self.BUSINESS_HOLIDAY_DIVISIONS:
                business_dates.append(calendar_date)

        return sorted(set(business_dates))

    def _request(
        self,
        start_date: date,
        end_date: date,
    ) -> JsonResponse:
        """取引カレンダーAPIへリクエストする。"""

        query = urlencode(
            {
                "from": start_date.strftime("%Y%m%d"),
                "to": end_date.strftime("%Y%m%d"),
            }
        )

        request = Request(
            url=(f"{JQUANTS_BASE_URL}{TRADING_CALENDAR_ENDPOINT}?{query}"),
            method="GET",
            headers={
                "x-api-key": self.api_key,
                "Accept": "application/json",
                "User-Agent": "Project-KATANA/0.27.0",
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
        """標準ライブラリでJSONを取得する。"""

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

            raise JQuantsCalendarError(
                "J-Quants取引カレンダーAPIが"
                "HTTPエラーを返しました。"
                f" status={error.code} body={error_body}"
            ) from error

        except URLError as error:
            raise JQuantsCalendarError(
                "J-Quants取引カレンダーAPIへ"
                "接続できませんでした。"
                f" reason={error.reason}"
            ) from error

        try:
            parsed = json.loads(response_text)
        except json.JSONDecodeError as error:
            raise JQuantsCalendarError(
                "取引カレンダーAPIから不正なJSONが返されました。"
            ) from error

        if not isinstance(parsed, dict):
            raise JQuantsCalendarError(
                "取引カレンダーAPIから想定外の形式が返されました。"
            )

        return parsed
