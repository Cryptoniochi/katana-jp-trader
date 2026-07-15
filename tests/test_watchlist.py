"""Watch List読込処理のテスト。"""

from pathlib import Path

import pytest

from app.watchlist import WatchlistError, load_watchlist


def write_watchlist(
    tmp_path: Path,
    content: str,
) -> Path:
    """テスト用Watch Listを書き込む。"""

    file_path = tmp_path / "watchlist.txt"
    file_path.write_text(
        content,
        encoding="utf-8",
    )

    return file_path


def test_load_watchlist_reads_codes(
    tmp_path: Path,
) -> None:
    """1行ずつ記載された銘柄コードを読み込む。"""

    file_path = write_watchlist(
        tmp_path,
        "7203\n8306\n6758\n",
    )

    assert load_watchlist(file_path) == [
        "7203",
        "8306",
        "6758",
    ]


def test_load_watchlist_ignores_comments_and_blank_lines(
    tmp_path: Path,
) -> None:
    """コメント行と空行を無視する。"""

    file_path = write_watchlist(
        tmp_path,
        """
# 自動車
7203

# 銀行
8306
""",
    )

    assert load_watchlist(file_path) == [
        "7203",
        "8306",
    ]


def test_load_watchlist_supports_inline_comments(
    tmp_path: Path,
) -> None:
    """銘柄コードの後ろのコメントを無視する。"""

    file_path = write_watchlist(
        tmp_path,
        """
7203  # トヨタ
8306  # 三菱UFJ
""",
    )

    assert load_watchlist(file_path) == [
        "7203",
        "8306",
    ]


def test_load_watchlist_supports_comma_separated_codes(
    tmp_path: Path,
) -> None:
    """カンマ区切りの銘柄コードを読み込む。"""

    file_path = write_watchlist(
        tmp_path,
        "7203, 8306, 6758\n",
    )

    assert load_watchlist(file_path) == [
        "7203",
        "8306",
        "6758",
    ]


def test_load_watchlist_removes_duplicates(
    tmp_path: Path,
) -> None:
    """重複コードを最初の1件だけ残す。"""

    file_path = write_watchlist(
        tmp_path,
        "7203\n8306\n7203\n",
    )

    assert load_watchlist(file_path) == [
        "7203",
        "8306",
    ]


def test_load_watchlist_accepts_five_digit_code(
    tmp_path: Path,
) -> None:
    """5桁の銘柄コードを読み込める。"""

    file_path = write_watchlist(
        tmp_path,
        "13010\n",
    )

    assert load_watchlist(file_path) == ["13010"]


def test_load_watchlist_rejects_non_numeric_code(
    tmp_path: Path,
) -> None:
    """数字以外を含む銘柄コードを拒否する。"""

    file_path = write_watchlist(
        tmp_path,
        "7203\nABCD\n",
    )

    with pytest.raises(
        WatchlistError,
        match="数字",
    ):
        load_watchlist(file_path)


def test_load_watchlist_rejects_invalid_length(
    tmp_path: Path,
) -> None:
    """4桁・5桁以外の銘柄コードを拒否する。"""

    file_path = write_watchlist(
        tmp_path,
        "720\n",
    )

    with pytest.raises(
        WatchlistError,
        match="4桁または5桁",
    ):
        load_watchlist(file_path)


def test_load_watchlist_rejects_empty_file(
    tmp_path: Path,
) -> None:
    """有効な銘柄がないWatch Listを拒否する。"""

    file_path = write_watchlist(
        tmp_path,
        "# コメントのみ\n\n",
    )

    with pytest.raises(
        WatchlistError,
        match="銘柄コードがありません",
    ):
        load_watchlist(file_path)


def test_load_watchlist_rejects_missing_file(
    tmp_path: Path,
) -> None:
    """存在しないWatch Listを拒否する。"""

    file_path = tmp_path / "missing.txt"

    with pytest.raises(
        FileNotFoundError,
        match="見つかりません",
    ):
        load_watchlist(file_path)
