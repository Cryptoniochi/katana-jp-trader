"""J-Quants取引カレンダーClientのテスト。"""

from datetime import date
from urllib.parse import parse_qs, urlparse
from urllib.request import Request

import pytest

from app.market.jquants_calendar import (
    JQuantsCalendarError,
    JQuantsTradingCalendarClient,
)


def test_client_returns_tse_business_dates() -> None:
    """通常営業日と半日立会日だけを返す。"""

    def fake_http_getter(
        request: Request,
        timeout_seconds: float,
    ) -> dict[str, object]:
        assert timeout_seconds == 30.0
        assert request.headers["X-api-key"] == "test-key"

        return {
            "data": [
                {
                    "Date": "2026-07-11",
                    "HolDiv": "0",
                },
                {
                    "Date": "2026-07-13",
                    "HolDiv": "1",
                },
                {
                    "Date": "2026-07-14",
                    "HolDiv": "2",
                },
                {
                    "Date": "2026-07-15",
                    "HolDiv": "3",
                },
            ]
        }

    client = JQuantsTradingCalendarClient(
        api_key="test-key",
        http_getter=fake_http_getter,
    )

    result = client.get_business_dates(
        start_date=date(2026, 7, 11),
        end_date=date(2026, 7, 15),
    )

    assert result == [
        date(2026, 7, 13),
        date(2026, 7, 14),
    ]


def test_client_sends_date_range_parameters() -> None:
    """fromとtoをYYYYMMDD形式で送信する。"""

    requested_query: dict[
        str,
        list[str],
    ] = {}

    def fake_http_getter(
        request: Request,
        _timeout_seconds: float,
    ) -> dict[str, object]:
        requested_query.update(parse_qs(urlparse(request.full_url).query))

        return {"data": []}

    client = JQuantsTradingCalendarClient(
        api_key="test-key",
        http_getter=fake_http_getter,
    )

    client.get_business_dates(
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 31),
    )

    assert requested_query["from"] == ["20260701"]
    assert requested_query["to"] == ["20260731"]


def test_client_removes_duplicate_dates() -> None:
    """重複した営業日を除去する。"""

    def fake_http_getter(
        _request: Request,
        _timeout_seconds: float,
    ) -> dict[str, object]:
        return {
            "data": [
                {
                    "Date": "2026-07-13",
                    "HolDiv": "1",
                },
                {
                    "Date": "2026-07-13",
                    "HolDiv": "1",
                },
            ]
        }

    client = JQuantsTradingCalendarClient(
        api_key="test-key",
        http_getter=fake_http_getter,
    )

    result = client.get_business_dates(
        start_date=date(2026, 7, 13),
        end_date=date(2026, 7, 13),
    )

    assert result == [date(2026, 7, 13)]


def test_client_rejects_invalid_response_data() -> None:
    """dataが一覧形式でなければ拒否する。"""

    def fake_http_getter(
        _request: Request,
        _timeout_seconds: float,
    ) -> dict[str, object]:
        return {
            "data": "invalid",
        }

    client = JQuantsTradingCalendarClient(
        api_key="test-key",
        http_getter=fake_http_getter,
    )

    with pytest.raises(
        JQuantsCalendarError,
        match="一覧形式",
    ):
        client.get_business_dates(
            start_date=date(2026, 7, 13),
            end_date=date(2026, 7, 13),
        )


def test_client_rejects_reversed_date_range() -> None:
    """開始日が終了日より後なら拒否する。"""

    client = JQuantsTradingCalendarClient(
        api_key="test-key",
    )

    with pytest.raises(
        ValueError,
        match="開始日",
    ):
        client.get_business_dates(
            start_date=date(2026, 7, 14),
            end_date=date(2026, 7, 13),
        )


def test_client_requires_api_key() -> None:
    """APIキーがなければ初期化できない。"""

    with pytest.raises(
        ValueError,
        match="APIキー",
    ):
        JQuantsTradingCalendarClient(api_key="")
