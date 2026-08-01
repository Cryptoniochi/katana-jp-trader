"""run_katana_serviceのテスト。"""

from pathlib import Path

from app.run_katana_service import (
    build_argument_parser,
)


def test_paper_trading_is_opt_in() -> None:
    arguments = build_argument_parser().parse_args(
        []
    )

    assert not arguments.enable_paper_trading
    assert arguments.database_path == Path(
        "data/katana.db"
    )


def test_parser_accepts_kabu_station_strategies() -> None:
    arguments = build_argument_parser().parse_args(
        [
            "--enable-paper-trading",
            "--strategy",
            "orb",
            "--strategy",
            "high-breakout",
        ]
    )

    assert arguments.enable_paper_trading
    assert arguments.strategy == [
        "orb",
        "high-breakout",
    ]
