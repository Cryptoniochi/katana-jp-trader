"""run_build_daily_barsのテスト。"""

from pathlib import Path

from app.run_build_daily_bars import (
    _resolve_codes,
    build_argument_parser,
)


def test_parser_accepts_codes_and_interval() -> None:
    arguments = build_argument_parser().parse_args(
        [
            "--code",
            "7203",
            "--code",
            "6758",
            "--source-interval-minutes",
            "5",
        ]
    )

    assert arguments.code == [
        "7203",
        "6758",
    ]
    assert arguments.source_interval_minutes == 5


def test_resolve_codes_reads_watchlist(
    tmp_path: Path,
) -> None:
    watchlist = tmp_path / "watchlist.txt"
    watchlist.write_text(
        "7203\n# comment\n6758\n7203\n",
        encoding="utf-8",
    )

    assert _resolve_codes(
        direct_codes=(),
        watchlist_path=watchlist,
    ) == (
        "7203",
        "6758",
    )
