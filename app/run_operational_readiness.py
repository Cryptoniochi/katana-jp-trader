"""Project KATANA運用準備チェックCLI。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from app.dashboard.katana_service_status_reader import (
    KatanaServiceStatusReader,
)
from app.runtime.operational_readiness_service import (
    OperationalReadinessService,
)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Project KATANAの日次運用準備状態を確認します。"
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
        default=Path("watchlist.txt"),
    )
    parser.add_argument(
        "--service-status-path",
        type=Path,
        default=Path(
            "reports/service/katana_service_status.json"
        ),
    )
    parser.add_argument(
        "--output-path",
        type=Path,
        default=Path(
            "reports/service/operational_readiness.json"
        ),
    )
    return parser


def run(
    arguments: Sequence[str] | None = None,
) -> int:
    parsed = build_argument_parser().parse_args(
        arguments
    )
    payload = OperationalReadinessService(
        database_path=parsed.database_path,
        watchlist_path=parsed.watchlist_path,
        service_status_reader=(
            KatanaServiceStatusReader(
                parsed.service_status_path
            )
        ),
    ).evaluate()

    parsed.output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    parsed.output_path.write_text(
        json.dumps(
            payload.to_dict(),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("Operational readiness check completed.")
    print(
        f"overall_state={payload.overall_state}"
    )
    print(
        "ready_for_paper_trading="
        f"{payload.ready_for_paper_trading}"
    )

    for check in payload.checks:
        print(
            f"{check.level.value.upper():7} "
            f"{check.label}: {check.message}"
        )

    print(parsed.output_path)

    return (
        0
        if payload.overall_state != "blocked"
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(run())
