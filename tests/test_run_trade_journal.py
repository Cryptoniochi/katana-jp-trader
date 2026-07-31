"""run_trade_journalのテスト。"""

from pathlib import Path

from app.run_trade_journal import (
    build_argument_parser,
)


def test_parser_accepts_database_and_interval() -> None:
    arguments = build_argument_parser().parse_args(
        [
            "--database-path",
            "data/test.db",
            "--market-bar-interval-minutes",
            "5",
        ]
    )

    assert arguments.database_path == Path(
        "data/test.db"
    )
    assert (
        arguments.market_bar_interval_minutes
        == 5
    )
