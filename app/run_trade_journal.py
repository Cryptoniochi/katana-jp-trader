"""Trade Journal再構築CLI。"""

from __future__ import annotations

import argparse
from pathlib import Path

from app.database import initialize_database
from app.trading.trade_journal_service import (
    TradeJournalService,
)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "保存済み約定からTrade Journalを再構築します。"
        )
    )
    parser.add_argument(
        "--database-path",
        type=Path,
        default=Path("data/katana.db"),
    )
    parser.add_argument(
        "--market-bar-interval-minutes",
        type=int,
        default=5,
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

    entries = TradeJournalService(
        parsed.database_path,
        market_bar_interval_minutes=(
            parsed.market_bar_interval_minutes
        ),
    ).rebuild()

    print("Trade Journal rebuild completed.")
    print(f"completed_trades={len(entries)}")

    if entries:
        print(
            "net_profit_loss="
            f"{sum(entry.realized_profit_loss for entry in entries):.2f}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(run())
