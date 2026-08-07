"""JPX上場銘柄マスター取込のテスト。"""

from datetime import datetime, timezone
from pathlib import Path

from app.universe.jpx_listed_symbol_importer import (
    JpxListedSymbolImporter,
)
from app.universe.listed_symbol_repository import (
    ListedSymbolRepository,
)


NOW = datetime(
    2026,
    8,
    7,
    tzinfo=timezone.utc,
)


def test_imports_only_domestic_common_stocks(
    tmp_path: Path,
) -> None:
    csv_path = tmp_path / "listed.csv"
    csv_path.write_text(
        "\n".join(
            (
                "コード,銘柄名,市場・商品区分",
                "7203,トヨタ自動車,プライム（内国株式）",
                "1306,NEXT FUNDS TOPIX,ETF・ETN",
                "607A,エブリー,グロース（内国株式）",
                "9999,Foreign Corp,スタンダード（外国株式）",
            )
        ),
        encoding="utf-8-sig",
    )

    result = JpxListedSymbolImporter(
        database_path=tmp_path / "katana.db",
        now_provider=lambda: NOW,
    ).import_file(csv_path)

    assert result.imported_count == 2
    assert result.prime_count == 1
    assert result.growth_count == 1

    repository = ListedSymbolRepository(
        tmp_path / "katana.db"
    )
    symbols = repository.load_active(
        allowed_markets=(
            "Prime",
            "Standard",
            "Growth",
        ),
        allowed_security_types=(
            "common_stock",
        ),
    )

    assert [item.code for item in symbols] == [
        "607A",
        "7203",
    ]


def test_snapshot_deactivates_missing_symbol(
    tmp_path: Path,
) -> None:
    first = tmp_path / "first.csv"
    first.write_text(
        "\n".join(
            (
                "コード,銘柄名,市場・商品区分",
                "7203,トヨタ自動車,プライム（内国株式）",
                "8306,三菱ＵＦＪ,プライム（内国株式）",
            )
        ),
        encoding="utf-8-sig",
    )
    second = tmp_path / "second.csv"
    second.write_text(
        "\n".join(
            (
                "コード,銘柄名,市場・商品区分",
                "7203,トヨタ自動車,プライム（内国株式）",
            )
        ),
        encoding="utf-8-sig",
    )

    importer = JpxListedSymbolImporter(
        database_path=tmp_path / "katana.db",
        now_provider=lambda: NOW,
    )
    importer.import_file(first)
    importer.import_file(second)

    repository = ListedSymbolRepository(
        tmp_path / "katana.db"
    )
    assert repository.count() == 2
    assert repository.count(active_only=True) == 1


def test_discovers_data_j_excel_link() -> None:
    page_html = """
    <html>
      <a href="/foo/topix.xlsx">TOPIX</a>
      <a href="/bar/data_j.xls">東証上場銘柄一覧</a>
    </html>
    """

    url = JpxListedSymbolImporter._discover_workbook_url(
        page_url="https://www.jpx.co.jp/example/01.html",
        page_html=page_html,
    )

    assert url == "https://www.jpx.co.jp/bar/data_j.xls"
