"""Project KATANA運用メンテナンスCLI。"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from app.runtime.operational_log_rotation import (
    rotate_operational_logs,
)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Project KATANAの主要ログを世代管理します。"
        )
    )
    parser.add_argument(
        "--project-directory",
        type=Path,
        default=Path.cwd(),
    )
    parser.add_argument(
        "--maximum-megabytes",
        type=float,
        default=5.0,
    )
    parser.add_argument(
        "--backup-count",
        type=int,
        default=5,
    )
    return parser


def run(
    arguments: Sequence[str] | None = None,
) -> int:
    parsed = build_argument_parser().parse_args(
        arguments
    )

    if parsed.maximum_megabytes <= 0:
        raise ValueError(
            "最大ログサイズは0より大きい必要があります。"
        )

    results = rotate_operational_logs(
        project_directory=(
            parsed.project_directory
        ),
        maximum_bytes=int(
            parsed.maximum_megabytes
            * 1024
            * 1024
        ),
        backup_count=parsed.backup_count,
    )

    print("KATANA operational maintenance completed.")

    for result in results:
        print(
            f"{result.path}: "
            f"existed={result.existed} "
            f"size={result.original_size} "
            f"rotated={result.rotated}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(run())
