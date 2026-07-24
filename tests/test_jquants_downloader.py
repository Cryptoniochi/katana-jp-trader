"""J-Quants分足Downloaderのテスト。"""

from io import BytesIO
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse
from urllib.request import Request

import pytest

from app.market.jquants_downloader import (
    JQuantsDownloadError,
    JQuantsMinuteDownloader,
)


def test_downloader_converts_rows_to_stock_prices() -> None:
    """J-Quantsの1分足をStockPriceへ変換できる。"""

    def fake_http_getter(
        request: Request,
        timeout_seconds: float,
    ) -> dict[str, object]:
        assert timeout_seconds == 30.0
        assert request.headers["X-api-key"] == "test-key"

        return {
            "data": [
                {
                    "Date": "2026-07-13",
                    "Time": "09:00",
                    "Code": "72030",
                    "O": 2844.0,
                    "H": 2847.0,
                    "L": 2830.0,
                    "C": 2838.5,
                    "Vo": 1_260_000.0,
                    "Va": 3_582_036_450.0,
                },
                {
                    "Date": "2026-07-13",
                    "Time": "09:01",
                    "Code": "72030",
                    "O": 2838.5,
                    "H": 2840.0,
                    "L": 2835.0,
                    "C": 2839.0,
                    "Vo": 200_000.0,
                    "Va": 567_800_000.0,
                },
            ],
        }

    downloader = JQuantsMinuteDownloader(
        api_key="test-key",
        http_getter=fake_http_getter,
    )

    prices = downloader.download(
        code="7203",
        date="2026-07-13",
    )

    assert len(prices) == 2

    assert prices[0].code == "7203"
    assert prices[0].datetime.isoformat() == ("2026-07-13T09:00:00")
    assert prices[0].open == pytest.approx(2844.0)
    assert prices[0].high == pytest.approx(2847.0)
    assert prices[0].low == pytest.approx(2830.0)
    assert prices[0].close == pytest.approx(2838.5)
    assert prices[0].volume == 1_260_000


def test_downloader_follows_pagination_key() -> None:
    """pagination_keyを使い全ページ取得できる。"""

    requested_queries: list[dict[str, list[str]]] = []

    def fake_http_getter(
        request: Request,
        _timeout_seconds: float,
    ) -> dict[str, object]:
        query = parse_qs(urlparse(request.full_url).query)
        requested_queries.append(query)

        if "pagination_key" not in query:
            return {
                "data": [
                    {
                        "Date": "2026-07-13",
                        "Time": "09:00",
                        "Code": "72030",
                        "O": 1000.0,
                        "H": 1005.0,
                        "L": 995.0,
                        "C": 1000.0,
                        "Vo": 100_000.0,
                        "Va": 100_000_000.0,
                    }
                ],
                "pagination_key": "next-page",
            }

        return {
            "data": [
                {
                    "Date": "2026-07-13",
                    "Time": "09:01",
                    "Code": "72030",
                    "O": 1000.0,
                    "H": 1006.0,
                    "L": 999.0,
                    "C": 1005.0,
                    "Vo": 120_000.0,
                    "Va": 120_600_000.0,
                }
            ]
        }

    downloader = JQuantsMinuteDownloader(
        api_key="test-key",
        http_getter=fake_http_getter,
    )

    prices = downloader.download(
        code="7203",
        date="20260713",
    )

    assert len(prices) == 2
    assert len(requested_queries) == 2

    assert requested_queries[0]["code"] == ["7203"]
    assert requested_queries[0]["date"] == ["20260713"]

    assert requested_queries[1]["pagination_key"] == ["next-page"]


def test_downloader_removes_duplicate_bars() -> None:
    """同一銘柄・同一時刻の重複足を除去する。"""

    duplicate_row = {
        "Date": "2026-07-13",
        "Time": "09:00",
        "Code": "72030",
        "O": 1000.0,
        "H": 1005.0,
        "L": 995.0,
        "C": 1000.0,
        "Vo": 100_000.0,
        "Va": 100_000_000.0,
    }

    def fake_http_getter(
        _request: Request,
        _timeout_seconds: float,
    ) -> dict[str, object]:
        return {
            "data": [
                duplicate_row,
                duplicate_row,
            ]
        }

    downloader = JQuantsMinuteDownloader(
        api_key="test-key",
        http_getter=fake_http_getter,
    )

    prices = downloader.download(
        code="7203",
        date="20260713",
    )

    assert len(prices) == 1


def test_downloader_rejects_missing_required_field() -> None:
    """必須項目のない行を拒否する。"""

    def fake_http_getter(
        _request: Request,
        _timeout_seconds: float,
    ) -> dict[str, object]:
        return {
            "data": [
                {
                    "Date": "2026-07-13",
                    "Time": "09:00",
                    "Code": "72030",
                }
            ]
        }

    downloader = JQuantsMinuteDownloader(
        api_key="test-key",
        http_getter=fake_http_getter,
    )

    with pytest.raises(
        JQuantsDownloadError,
        match="必須項目",
    ):
        downloader.download(
            code="7203",
            date="20260713",
        )


@pytest.mark.parametrize(
    ("code", "date", "message"),
    [
        ("", "20260713", "銘柄コード"),
        ("ABCD", "20260713", "銘柄コード"),
        ("720", "20260713", "4桁または5桁"),
        ("7203", "2026/07/13", "日付"),
    ],
)
def test_downloader_rejects_invalid_arguments(
    code: str,
    date: str,
    message: str,
) -> None:
    """不正な銘柄コードまたは日付を拒否する。"""

    downloader = JQuantsMinuteDownloader(api_key="test-key")

    with pytest.raises(ValueError, match=message):
        downloader.download(
            code=code,
            date=date,
        )


def test_downloader_requires_api_key() -> None:
    """APIキーがなければ初期化できない。"""

    with pytest.raises(ValueError, match="APIキー"):
        JQuantsMinuteDownloader(api_key="")



def test_default_http_getter_preserves_rate_limit_metadata() -> None:
    """HTTP 429とRetry-Afterを例外情報へ保持する。"""

    error = HTTPError(
        url="https://example.test",
        code=429,
        msg="Too Many Requests",
        hdrs={"Retry-After": "45"},
        fp=BytesIO(b'{"message":"Rate limit exceeded"}'),
    )

    def fake_urlopen(*_args, **_kwargs):
        raise error

    import app.market.jquants_downloader as module

    original = module.urlopen
    module.urlopen = fake_urlopen

    try:
        with pytest.raises(
            JQuantsDownloadError,
        ) as captured:
            JQuantsMinuteDownloader._default_http_getter(
                Request("https://example.test"),
                30.0,
            )
    finally:
        module.urlopen = original

    assert captured.value.status_code == 429
    assert captured.value.is_rate_limited is True
    assert captured.value.retry_after_seconds == 45.0


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        ("", None),
        ("15", 15.0),
        ("1.5", 1.5),
        ("-1", None),
        ("invalid", None),
    ],
)
def test_parse_retry_after_seconds(
    value: str | None,
    expected: float | None,
) -> None:
    """Retry-Afterの秒数表現を安全に解析する。"""

    assert (
        JQuantsMinuteDownloader
        ._parse_retry_after_seconds(value)
        == expected
    )
