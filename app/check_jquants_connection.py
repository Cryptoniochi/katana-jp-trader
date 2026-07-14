"""J-Quants API V2の接続と分足権限を確認する。"""

import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE_URL = "https://api.jquants.com/v2"
MINUTE_BARS_ENDPOINT = "/equities/bars/minute"


def get_api_key() -> str:
    """環境変数からJ-Quants APIキーを取得する。"""

    api_key = os.getenv("JQUANTS_API_KEY", "").strip()

    if not api_key:
        raise RuntimeError("環境変数 JQUANTS_API_KEY が設定されていません。")

    return api_key


def request_minute_bars(
    api_key: str,
    code: str,
    date: str,
) -> dict[str, object]:
    """指定銘柄・日付の1分足をJ-Quantsから取得する。"""

    query = urlencode(
        {
            "code": code,
            "date": date,
        }
    )

    url = f"{BASE_URL}{MINUTE_BARS_ENDPOINT}?{query}"

    request = Request(
        url=url,
        method="GET",
        headers={
            "x-api-key": api_key,
            "Accept": "application/json",
            "User-Agent": "Project-KATANA/0.21.0",
        },
    )

    try:
        with urlopen(request, timeout=30) as response:
            response_text = response.read().decode("utf-8")

    except HTTPError as error:
        error_body = error.read().decode(
            "utf-8",
            errors="replace",
        )

        raise RuntimeError(
            "J-Quants APIがHTTPエラーを返しました。"
            f" status={error.code} body={error_body}"
        ) from error

    except URLError as error:
        raise RuntimeError(
            f"J-Quants APIへ接続できませんでした。 reason={error.reason}"
        ) from error

    parsed = json.loads(response_text)

    if not isinstance(parsed, dict):
        raise RuntimeError("J-Quants APIから想定外の形式が返されました。")

    return parsed


def main() -> None:
    """7203の1分足を取得し、接続結果を表示する。"""

    api_key = get_api_key()

    response = request_minute_bars(
        api_key=api_key,
        code="7203",
        date="20260713",
    )

    raw_data = response.get("data", [])

    if not isinstance(raw_data, list):
        raise RuntimeError("レスポンスのdataが一覧形式ではありません。")

    print("=" * 50)
    print("J-Quants connection successful")
    print("=" * 50)
    print(f"records: {len(raw_data)}")

    if not raw_data:
        print("指定日の分足データは0件でした。")
        print("休場日、データ提供時刻、契約反映状況を確認してください。")
        return

    print("first:")
    print(raw_data[0])

    print("last:")
    print(raw_data[-1])

    pagination_key = response.get("pagination_key")

    if pagination_key:
        print("pagination_key: returned")
    else:
        print("pagination_key: none")


if __name__ == "__main__":
    main()
