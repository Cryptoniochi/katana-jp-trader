"""ListedSymbolCsvImporterのテスト。"""

from pathlib import Path

from app.universe.listed_symbol_csv_importer import (
    ListedSymbolCsvImporter,
)
from app.universe.listed_symbol_repository import (
    ListedSymbolRepository,
)


def test_imports_japanese_headers(
    tmp_path: Path,
) -> None:
    csv_path = tmp_path / "symbols.csv"
    database = tmp_path / "katana.db"
    csv_path.write_text(
        "\n".join(
            [
                "銘柄コード,銘柄名,市場区分,商品区分,単元株数",
                "7203,トヨタ自動車,プライム,普通株,100",
                "1234,テストETF,プライム,ETF,1",
            ]
        ),
        encoding="utf-8",
    )

    imported = ListedSymbolCsvImporter(
        database_path=database
    ).import_file(csv_path)

    active = ListedSymbolRepository(
        database
    ).load_active(
        allowed_markets=("Prime",),
        allowed_security_types=(
            "common_stock",
        ),
    )

    assert len(imported) == 2
    assert [item.code for item in active] == [
        "7203"
    ]
