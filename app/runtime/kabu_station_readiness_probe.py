"""kabuステーションProduction Readinessを定期確認する。"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class KabuStationReadinessResult:
    """Readiness Probeの結果。"""

    state: str
    exit_code: int | None
    message: str


def probe_kabu_station_readiness(
    *,
    timeout_seconds: float = 20.0,
) -> KabuStationReadinessResult:
    """既存の`run_paper_trading --check`を安全に実行する。"""

    if timeout_seconds <= 0:
        raise ValueError(
            "タイムアウトは0より大きい必要があります。"
        )

    try:
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "app.run_paper_trading",
                "--check",
            ],
            check=False,
            cwd=Path.cwd(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return KabuStationReadinessResult(
            state="timeout",
            exit_code=None,
            message=(
                "kabuステーションReadiness Checkが"
                "タイムアウトしました。"
            ),
        )
    except OSError as error:
        return KabuStationReadinessResult(
            state="error",
            exit_code=None,
            message=str(error),
        )

    if completed.returncode == 0:
        return KabuStationReadinessResult(
            state="connected",
            exit_code=0,
            message="kabuステーション接続確認済み。",
        )

    details = (
        completed.stderr.strip()
        or completed.stdout.strip()
        or "Readiness Check failed."
    )

    return KabuStationReadinessResult(
        state="disconnected",
        exit_code=int(completed.returncode),
        message=details[-500:],
    )
