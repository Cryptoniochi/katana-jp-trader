"""多重起動防止とStatus書込み耐障害性を備えたKATANA Service入口。"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Sequence

import app.run_katana_service as original_service
from app.runtime.katana_service_hardening import (
    ResilientKatanaServiceManager,
    ServiceAlreadyRunningError,
    ServiceInstanceLock,
)


DEFAULT_LOCK_PATH = Path(
    "reports/service/katana_service.lock"
)


def run(
    arguments: Sequence[str] | None = None,
) -> int:
    lock = ServiceInstanceLock(
        DEFAULT_LOCK_PATH
    )

    try:
        lock.acquire()
    except ServiceAlreadyRunningError as error:
        print(
            f"ERROR: {error}",
            file=sys.stderr,
        )
        return 2

    original_manager = (
        original_service.KatanaServiceManager
    )
    original_service.KatanaServiceManager = (
        ResilientKatanaServiceManager
    )

    try:
        return original_service.run(arguments)
    finally:
        original_service.KatanaServiceManager = (
            original_manager
        )
        lock.release()


if __name__ == "__main__":
    raise SystemExit(run())
