"""保存済み分足から日足を生成するCLI。"""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from app.database import initialize_database
from app.market.bar_repository import (
    MarketBarRepository,
)
from app.market.intraday_daily_bar_builder import (
    IntradayDailyBarBuilder,
)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "SQLiteに保存済みの分足から日足を生成します。"
        )
    )
    parser.add_argument(
        "--database-path",
        type=Path,
        default=Path("data/katana.db"),
    )
    parser.add_argument(
        "--source-interval-minutes",
        type=int,
        default=5,
    )
    parser.add_argument(
        "--code",
        action="append",
        default=[],
    )
    parser.add_argument(
        "--watchlist-path",
        type=Path,
        default=Path("config/watchlist.txt"),
    )
    parser.add_argument(
        "--start-at",
        type=datetime.fromisoformat,
        default=None,
    )
    parser.add_argument(
        "--end-at",
        type=datetime.fromisoformat,
        default=None,
    )
    return parser


def run(
    arguments: list[str] | None = None,
) -> int:
    parsed = build_argument_parser().parse_args(
        arguments
    )
    initialize_database(
        parsed.database_path
    )

    codes = _resolve_codes(
        direct_codes=tuple(parsed.code),
        watchlist_path=parsed.watchlist_path,
    )
    result = IntradayDailyBarBuilder(
        repository=MarketBarRepository(
            parsed.database_path
        ),
        source_interval_minutes=(
            parsed.source_interval_minutes
        ),
    ).build(
        codes=codes,
        start_at=parsed.start_at,
        end_at=parsed.end_at,
    )

    print("Daily bar build completed.")
    print(f"Codes: {result.code_count}")
    print(
        "Source bars: "
        f"{result.source_bar_count}"
    )
    print(
        "Daily bars: "
        f"{result.daily_bar_count}"
    )
    print(
        "Saved bars: "
        f"{result.saved_bar_count}"
    )
    return 0


def _resolve_codes(
    *,
    direct_codes: tuple[str, ...],
    watchlist_path: Path,
) -> tuple[str, ...]:
    if direct_codes:
        values = direct_codes
    else:
        if not watchlist_path.exists():
            raise ValueError(
                "Watchlistが存在しません。 "
                f"path={watchlist_path}"
            )

        values = tuple(
            line.strip()
            for line in watchlist_path.read_text(
                encoding="utf-8"
            ).splitlines()
            if (
                line.strip()
                and not line.strip().startswith("#")
            )
        )

    normalized = tuple(
        dict.fromkeys(
            value.strip()
            for value in values
            if value.strip()
        )
    )

    if not normalized:
        raise ValueError(
            "銘柄コードを1件以上指定してください。"
        )

    return normalized


if __name__ == "__main__":
    raise SystemExit(run())
