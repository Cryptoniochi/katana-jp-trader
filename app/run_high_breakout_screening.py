"""新高値ブレイク候補抽出を実行するCLI。"""

from __future__ import annotations

import argparse
from pathlib import Path

from app.database import initialize_database
from app.market.bar_repository import (
    MarketBarRepository,
)
from app.strategy.high_breakout_candidate_repository import (
    HighBreakoutCandidateRepository,
)
from app.strategy.high_breakout_models import (
    HighBreakoutScreenerSettings,
)
from app.strategy.high_breakout_reporter import (
    HighBreakoutReporter,
)
from app.strategy.high_breakout_screener import (
    HighBreakoutScreener,
)
from app.strategy.high_breakout_screening_service import (
    HighBreakoutScreeningService,
)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "日足データから新高値ブレイク候補を"
            "抽出して保存・レポート出力します。"
        )
    )
    parser.add_argument(
        "--database-path",
        type=Path,
        default=Path("data/katana.db"),
    )
    parser.add_argument(
        "--csv-path",
        type=Path,
        default=None,
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
        "--output-directory",
        type=Path,
        default=Path("reports/high_breakout"),
    )
    parser.add_argument(
        "--minimum-volume-ratio",
        type=float,
        default=1.5,
    )
    parser.add_argument(
        "--minimum-turnover",
        type=float,
        default=100_000_000.0,
    )
    parser.add_argument(
        "--minimum-price",
        type=float,
        default=300.0,
    )
    parser.add_argument(
        "--maximum-price",
        type=float,
        default=20_000.0,
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

    screener = HighBreakoutScreener(
        settings=HighBreakoutScreenerSettings(
            minimum_volume_ratio=(
                parsed.minimum_volume_ratio
            ),
            minimum_turnover=(
                parsed.minimum_turnover
            ),
            minimum_price=parsed.minimum_price,
            maximum_price=parsed.maximum_price,
        )
    )
    service = HighBreakoutScreeningService(
        screener=screener,
        candidate_repository=(
            HighBreakoutCandidateRepository(
                parsed.database_path
            )
        ),
    )

    if parsed.csv_path is not None:
        candidates = service.run_from_csv(
            parsed.csv_path
        )
    else:
        codes = _resolve_codes(
            direct_codes=tuple(parsed.code),
            watchlist_path=parsed.watchlist_path,
        )
        candidates = service.run_from_database(
            market_bar_repository=MarketBarRepository(
                parsed.database_path
            ),
            codes=codes,
        )

    paths = HighBreakoutReporter(
        parsed.output_directory
    ).write(candidates)

    print("High Breakout screening completed.")
    print(f"Candidates: {len(candidates)}")

    for path in paths:
        print(path)

    return 0


def _resolve_codes(
    *,
    direct_codes: tuple[str, ...],
    watchlist_path: Path,
) -> tuple[str, ...]:
    if direct_codes:
        codes = direct_codes
    else:
        if not watchlist_path.exists():
            raise ValueError(
                "監視銘柄が指定されておらず、"
                "Watchlistも存在しません。 "
                f"path={watchlist_path}"
            )

        codes = tuple(
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
            code.strip()
            for code in codes
            if code.strip()
        )
    )

    if not normalized:
        raise ValueError(
            "監視銘柄を1件以上指定してください。"
        )

    return normalized


if __name__ == "__main__":
    raise SystemExit(run())
