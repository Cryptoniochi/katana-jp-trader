"""High Breakout運用前処理を一括実行するCLI。"""

from __future__ import annotations

import argparse
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from app.run_build_daily_bars import run as run_build_daily_bars
from app.run_high_breakout_screening import (
    run as run_high_breakout_screening,
)


DAILY_INTERVAL_MINUTES = 1440


@dataclass(frozen=True, slots=True)
class HighBreakoutOperationResult:
    """High Breakout運用準備の結果。"""

    daily_bar_exit_code: int
    screening_exit_code: int
    daily_bar_count: int
    candidate_count: int
    paper_trading_started: bool

    @property
    def successful(self) -> bool:
        """全処理が正常終了したか返す。"""

        return (
            self.daily_bar_exit_code == 0
            and self.screening_exit_code == 0
        )


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "分足から日足を生成し、新高値候補を抽出した後、"
            "必要に応じてHigh Breakout Paper Tradingを起動します。"
        )
    )
    parser.add_argument(
        "--database-path",
        type=Path,
        default=Path("data/katana.db"),
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
        "--start-paper-trading",
        action="store_true",
    )
    parser.add_argument(
        "--paper-trading-dry-run",
        action="store_true",
        help=(
            "Paper Trading起動コマンドだけ表示し、"
            "実際には起動しません。"
        ),
    )
    return parser


def run(
    arguments: list[str] | None = None,
) -> int:
    parsed = build_argument_parser().parse_args(arguments)

    result = execute_operation(
        database_path=parsed.database_path,
        watchlist_path=parsed.watchlist_path,
        output_directory=parsed.output_directory,
        source_interval_minutes=(
            parsed.source_interval_minutes
        ),
        codes=tuple(parsed.code),
        minimum_volume_ratio=(
            parsed.minimum_volume_ratio
        ),
        minimum_turnover=parsed.minimum_turnover,
        start_paper_trading=parsed.start_paper_trading,
        paper_trading_dry_run=(
            parsed.paper_trading_dry_run
        ),
    )

    print("High Breakout operation completed.")
    print(
        "daily_bar_exit_code="
        f"{result.daily_bar_exit_code}"
    )
    print(
        "screening_exit_code="
        f"{result.screening_exit_code}"
    )
    print(
        f"daily_bar_count={result.daily_bar_count}"
    )
    print(
        f"candidate_count={result.candidate_count}"
    )
    print(
        "paper_trading_started="
        f"{result.paper_trading_started}"
    )

    return 0 if result.successful else 1


def execute_operation(
    *,
    database_path: Path,
    watchlist_path: Path,
    output_directory: Path,
    source_interval_minutes: int,
    codes: tuple[str, ...],
    minimum_volume_ratio: float,
    minimum_turnover: float,
    start_paper_trading: bool,
    paper_trading_dry_run: bool,
) -> HighBreakoutOperationResult:
    """日足生成、候補抽出、任意のPaper Trading起動を行う。"""

    if source_interval_minutes <= 0:
        raise ValueError(
            "元時間足の間隔は0より大きい必要があります。"
        )

    build_arguments = [
        "--database-path",
        str(database_path),
        "--watchlist-path",
        str(watchlist_path),
        "--source-interval-minutes",
        str(source_interval_minutes),
    ]

    for code in codes:
        build_arguments.extend(
            [
                "--code",
                code,
            ]
        )

    daily_bar_exit_code = run_build_daily_bars(
        build_arguments
    )

    screening_arguments = [
        "--database-path",
        str(database_path),
        "--watchlist-path",
        str(watchlist_path),
        "--output-directory",
        str(output_directory),
        "--minimum-volume-ratio",
        str(minimum_volume_ratio),
        "--minimum-turnover",
        str(minimum_turnover),
    ]

    for code in codes:
        screening_arguments.extend(
            [
                "--code",
                code,
            ]
        )

    screening_exit_code = (
        run_high_breakout_screening(
            screening_arguments
        )
    )

    daily_bar_count = _count_rows(
        database_path,
        """
        SELECT COUNT(*)
        FROM market_bars
        WHERE interval_minutes = ?
        """,
        (DAILY_INTERVAL_MINUTES,),
    )
    candidate_count = _count_rows(
        database_path,
        """
        SELECT COUNT(*)
        FROM high_breakout_candidates
        """,
        (),
    )

    paper_trading_started = False

    if start_paper_trading:
        command = [
            sys.executable,
            "-m",
            "app.run_paper_trading",
            "--strategy",
            "high-breakout",
        ]

        if codes:
            for code in codes:
                command.extend(
                    [
                        "--code",
                        code,
                    ]
                )

        if paper_trading_dry_run:
            print(
                "Paper Trading command: "
                + subprocess.list2cmdline(command)
            )
        elif candidate_count == 0:
            print(
                "High Breakout候補が0件のため、"
                "Paper Tradingは起動しません。"
            )
        else:
            subprocess.Popen(
                command,
                cwd=Path.cwd(),
            )
            paper_trading_started = True

    return HighBreakoutOperationResult(
        daily_bar_exit_code=daily_bar_exit_code,
        screening_exit_code=screening_exit_code,
        daily_bar_count=daily_bar_count,
        candidate_count=candidate_count,
        paper_trading_started=paper_trading_started,
    )


def _count_rows(
    database_path: Path,
    sql: str,
    parameters: tuple[object, ...],
) -> int:
    """SQLiteの件数を返す。"""

    if not database_path.exists():
        return 0

    with sqlite3.connect(
        database_path
    ) as connection:
        row = connection.execute(
            sql,
            parameters,
        ).fetchone()

    return int(row[0]) if row is not None else 0


if __name__ == "__main__":
    raise SystemExit(run())
