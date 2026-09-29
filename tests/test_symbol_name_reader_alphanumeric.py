import pytest

from app.dashboard.symbol_name_reader import (
    SymbolNameReader,
)


@pytest.mark.parametrize(
    ("raw_code", "expected"),
    [
        ("141A", "141A"),
        ("9A76", "9A76"),
        ("9A7A", "9A7A"),
        ("141a", "141A"),
        ("7203", "7203"),
        ("72030", "72030"),
    ],
)
def test_normalize_code_accepts_jpx_codes(
    raw_code: str,
    expected: str,
) -> None:
    assert (
        SymbolNameReader._normalize_code(raw_code)
        == expected
    )


@pytest.mark.parametrize(
    "raw_code",
    [
        "141B",
        "14A1",
        "ABC1",
        "123",
        "123456",
        "",
    ],
)
def test_normalize_code_rejects_invalid_codes(
    raw_code: str,
) -> None:
    with pytest.raises(ValueError):
        SymbolNameReader._normalize_code(raw_code)