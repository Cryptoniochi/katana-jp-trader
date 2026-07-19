"""Project KATANAの自動運用エントリーポイント。"""

from __future__ import annotations

import sys
from collections.abc import Mapping, Sequence
from typing import TextIO

from app.health_check import run as run_health_check
from app.run_market_session import run as run_market_session


def run(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    output: TextIO = sys.stdout,
    error_output: TextIO = sys.stderr,
    health_check_runner=run_health_check,
    market_session_runner=run_market_session,
) -> int:
    """Health Check成功後に市場セッション運用を開始する。"""

    arguments = list(argv or ())

    print(
        "Project KATANA Automated Scheduler",
        file=output,
    )
    print(
        "Health Checkを開始します。",
        file=output,
    )

    health_exit_code = int(
        health_check_runner(
            arguments,
            environ=environ,
            output=output,
            error_output=error_output,
        )
    )

    if health_exit_code != 0:
        print(
            "Health CheckがREADYではないため、"
            "Paper Tradingを開始しません。",
            file=error_output,
        )
        return health_exit_code

    print(
        "Health CheckはREADYです。"
        "市場セッション判定へ進みます。",
        file=output,
    )

    return int(
        market_session_runner(
            arguments,
            environ=environ,
            output=output,
            error_output=error_output,
        )
    )


def main() -> None:
    """CLIエントリーポイント。"""

    raise SystemExit(
        run(sys.argv[1:])
    )


if __name__ == "__main__":
    main()
