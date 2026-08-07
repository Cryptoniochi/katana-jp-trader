"""KabuStationSymbolの証券コード検証テスト。"""

import pytest

from app.market.kabu_station_models import KabuStationSymbol


@pytest.mark.parametrize(
    "value, expected",
    [
        ("7203", "7203"),
        ("130A", "130A"),
        ("607a", "607A"),
        ("12345", "12345"),
    ],
)
def test_kabu_station_symbol_accepts_current_jpx_codes(
    value: str,
    expected: str,
) -> None:
    assert KabuStationSymbol(value).code == expected


@pytest.mark.parametrize(
    "value",
    (
        "",
        "123",
        "ABCDEF",
        "12-A",
        "１２３４",
    ),
)
def test_kabu_station_symbol_rejects_invalid_codes(
    value: str,
) -> None:
    with pytest.raises(ValueError):
        KabuStationSymbol(value)
