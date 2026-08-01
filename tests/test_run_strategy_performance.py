"""run_strategy_performanceのテスト。"""

from pathlib import Path

from app.run_strategy_performance import (
    build_argument_parser,
)


def test_parser_accepts_paths() -> None:
    arguments = build_argument_parser().parse_args(
        [
            "--database-path",
            "data/test.db",
            "--output-path",
            "reports/test.json",
        ]
    )

    assert arguments.database_path == Path(
        "data/test.db"
    )
    assert arguments.output_path == Path(
        "reports/test.json"
    )
