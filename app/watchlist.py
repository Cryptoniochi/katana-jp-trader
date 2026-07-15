"""更新・分析対象の銘柄リストを読み込む処理。"""

from pathlib import Path


class WatchlistError(ValueError):
    """Watch Listの内容が不正であることを表す。"""


def load_watchlist(file_path: Path) -> list[str]:
    """Watch Listから銘柄コードを読み込む。"""

    if not file_path.exists():
        raise FileNotFoundError(f"Watch Listが見つかりません。path={file_path}")

    if not file_path.is_file():
        raise WatchlistError(
            f"Watch Listのパスがファイルではありません。path={file_path}"
        )

    content = file_path.read_text(
        encoding="utf-8-sig",
    )

    codes: list[str] = []

    for line_number, raw_line in enumerate(
        content.splitlines(),
        start=1,
    ):
        line_without_comment = raw_line.split(
            "#",
            maxsplit=1,
        )[0]

        tokens = line_without_comment.replace(",", " ").split()

        for token in tokens:
            code = token.strip()

            _validate_code(
                code=code,
                line_number=line_number,
            )

            if code not in codes:
                codes.append(code)

    if not codes:
        raise WatchlistError("Watch Listに銘柄コードがありません。")

    return codes


def _validate_code(
    code: str,
    line_number: int,
) -> None:
    """Watch List内の銘柄コードを検証する。"""

    if not code.isdigit():
        raise WatchlistError(
            f"銘柄コードは数字で指定してください。 line={line_number} value={code}"
        )

    if len(code) not in (4, 5):
        raise WatchlistError(
            "銘柄コードは4桁または5桁で指定してください。"
            f" line={line_number} value={code}"
        )
