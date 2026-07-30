"""kabuステーション実接続確認CLIのテスト。"""

import argparse

import pytest

from app.run_kabu_station_realtime_check import (
    normalize_codes,
    resolve_api_password,
)


def test_resolve_api_password() -> None:
    assert resolve_api_password(
        {
            "KABU_STATION_API_PASSWORD": " secret "
        }
    ) == "secret"


def test_resolve_api_password_requires_value() -> None:
    with pytest.raises(
        ValueError,
        match="KABU_STATION_API_PASSWORD",
    ):
        resolve_api_password({})


def test_normalize_codes_removes_duplicates() -> None:
    assert normalize_codes(
        ["7203", "9984", "7203"]
    ) == ("7203", "9984")


def test_normalize_codes_rejects_more_than_50() -> None:
    codes = [
        str(1000 + index)
        for index in range(51)
    ]

    with pytest.raises(ValueError, match="50銘柄"):
        normalize_codes(codes)
