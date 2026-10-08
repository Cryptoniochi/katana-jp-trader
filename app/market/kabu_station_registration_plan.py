"""Build the complete runtime subscription set before any API mutation."""
from collections.abc import Iterable


def build_registration_codes(
    watchlist_codes: Iterable[str],
    position_codes: Iterable[str],
    *,
    maximum_symbols: int = 50,
) -> tuple[str, ...]:
    if not 1 <= maximum_symbols <= 50:
        raise ValueError("API登録上限は1～50件で指定してください。")
    positions = tuple(dict.fromkeys(
        str(code).strip() for code in position_codes if str(code).strip()
    ))
    if len(positions) > maximum_symbols:
        raise ValueError("保有銘柄数がAPI登録上限を超えています。")
    watchlist = tuple(str(code).strip() for code in watchlist_codes
                      if str(code).strip())
    return tuple(dict.fromkeys((*positions, *watchlist)))[:maximum_symbols]
