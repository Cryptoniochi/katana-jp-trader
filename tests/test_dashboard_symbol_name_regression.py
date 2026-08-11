"""Sprint 127 dashboard symbol-name regression tests."""

from pathlib import Path

from app.dashboard.symbol_name_reader import SymbolNameReader


def test_symbol_label_source_is_available() -> None:
    reader = SymbolNameReader(
        Path("data/katana.db")
    )
    assert hasattr(reader, "resolve")
    assert hasattr(reader, "read_all")
