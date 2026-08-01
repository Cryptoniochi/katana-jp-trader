"""Project KATANAの日次運用準備状態を判定する。"""

from __future__ import annotations

import shutil
import sqlite3
import subprocess
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from app.runtime.operational_readiness_models import (
    OperationalReadinessPayload,
    ReadinessCheck,
    ReadinessLevel,
)


class OperationalReadinessService:
    """主要な運用依存関係を読み取り専用で確認する。"""

    def __init__(
        self,
        *,
        database_path: Path,
        watchlist_path: Path,
        service_status_reader,
        project_directory: Path = Path.cwd(),
        minimum_free_bytes: int = 2 * 1024 * 1024 * 1024,
        maximum_log_bytes: int = 5 * 1024 * 1024,
        now_provider: Callable[[], datetime] | None = None,
        tailscale_runner: Callable[..., subprocess.CompletedProcess] = (
            subprocess.run
        ),
    ) -> None:
        if minimum_free_bytes < 0:
            raise ValueError(
                "最低空き容量は0以上である必要があります。"
            )

        if maximum_log_bytes <= 0:
            raise ValueError(
                "最大ログサイズは0より大きい必要があります。"
            )

        self.database_path = Path(database_path)
        self.watchlist_path = Path(watchlist_path)
        self.service_status_reader = service_status_reader
        self.project_directory = Path(
            project_directory
        )
        self.minimum_free_bytes = minimum_free_bytes
        self.maximum_log_bytes = maximum_log_bytes
        self.now_provider = (
            now_provider
            if now_provider is not None
            else lambda: datetime.now(timezone.utc)
        )
        self.tailscale_runner = tailscale_runner

    def evaluate(
        self,
    ) -> OperationalReadinessPayload:
        """運用準備状態を集計して返す。"""

        service_payload = (
            self.service_status_reader.read()
        )
        checks = (
            self._check_service(
                service_payload
            ),
            self._check_database(),
            self._check_watchlist(),
            self._check_kabu_station(
                service_payload
            ),
            self._check_tailscale(),
            self._check_storage(),
            self._check_logs(),
        )

        required_failures = [
            check
            for check in checks
            if check.required
            and check.level is ReadinessLevel.FAIL
        ]
        warnings = [
            check
            for check in checks
            if check.level is ReadinessLevel.WARNING
        ]

        if required_failures:
            overall_state = "blocked"
        elif warnings:
            overall_state = "attention"
        else:
            overall_state = "ready"

        return OperationalReadinessPayload(
            generated_at=self._current_time(),
            overall_state=overall_state,
            ready_for_paper_trading=(
                not required_failures
                and all(
                    check.level is ReadinessLevel.PASS
                    for check in checks
                    if check.key
                    in {
                        "service",
                        "database",
                        "watchlist",
                        "kabu_station",
                    }
                )
            ),
            checks=checks,
        )

    def _check_service(
        self,
        payload: dict,
    ) -> ReadinessCheck:
        state = str(
            payload.get(
                "service_state",
                "unknown",
            )
        )
        stale = bool(
            payload.get(
                "stale",
                False,
            )
        )
        passed = (
            state == "healthy"
            and not stale
        )

        return ReadinessCheck(
            key="service",
            label="KATANA Service",
            level=(
                ReadinessLevel.PASS
                if passed
                else ReadinessLevel.FAIL
            ),
            message=(
                "Service Manager is healthy."
                if passed
                else (
                    "Service Manager is not healthy "
                    f"or status is stale. state={state}"
                )
            ),
            required=True,
            details={
                "state": state,
                "stale": stale,
                "age_seconds": payload.get(
                    "status_age_seconds"
                ),
            },
        )

    def _check_database(
        self,
    ) -> ReadinessCheck:
        if not self.database_path.exists():
            return ReadinessCheck(
                key="database",
                label="SQLite Database",
                level=ReadinessLevel.FAIL,
                message=(
                    "Database file does not exist."
                ),
                required=True,
                details={
                    "path": str(
                        self.database_path
                    ),
                },
            )

        try:
            with sqlite3.connect(
                self.database_path,
                timeout=2.0,
            ) as connection:
                connection.execute(
                    "SELECT 1"
                ).fetchone()
                integrity = connection.execute(
                    "PRAGMA quick_check"
                ).fetchone()
        except sqlite3.Error as error:
            return ReadinessCheck(
                key="database",
                label="SQLite Database",
                level=ReadinessLevel.FAIL,
                message=str(error),
                required=True,
                details={
                    "path": str(
                        self.database_path
                    ),
                },
            )

        result = (
            str(integrity[0])
            if integrity is not None
            else "unknown"
        )
        passed = result.lower() == "ok"

        return ReadinessCheck(
            key="database",
            label="SQLite Database",
            level=(
                ReadinessLevel.PASS
                if passed
                else ReadinessLevel.FAIL
            ),
            message=(
                "Database quick check passed."
                if passed
                else (
                    "Database quick check failed. "
                    f"result={result}"
                )
            ),
            required=True,
            details={
                "path": str(
                    self.database_path
                ),
                "quick_check": result,
                "size_bytes": (
                    self.database_path.stat().st_size
                ),
            },
        )

    def _check_watchlist(
        self,
    ) -> ReadinessCheck:
        if not self.watchlist_path.exists():
            return ReadinessCheck(
                key="watchlist",
                label="Watchlist",
                level=ReadinessLevel.FAIL,
                message="Watchlist file does not exist.",
                required=True,
                details={
                    "path": str(
                        self.watchlist_path
                    ),
                    "code_count": 0,
                },
            )

        lines = [
            line.strip()
            for line in self.watchlist_path.read_text(
                encoding="utf-8-sig"
            ).splitlines()
            if line.strip()
            and not line.strip().startswith("#")
        ]
        valid_codes = [
            line
            for line in lines
            if line.isdigit()
            and len(line) == 4
        ]
        invalid_codes = [
            line
            for line in lines
            if line not in valid_codes
        ]

        if not valid_codes:
            level = ReadinessLevel.FAIL
            message = (
                "No valid four-digit stock codes "
                "were found."
            )
        elif invalid_codes:
            level = ReadinessLevel.WARNING
            message = (
                "Watchlist contains invalid rows."
            )
        else:
            level = ReadinessLevel.PASS
            message = (
                f"Watchlist is ready. "
                f"codes={len(valid_codes)}"
            )

        return ReadinessCheck(
            key="watchlist",
            label="Watchlist",
            level=level,
            message=message,
            required=True,
            details={
                "path": str(
                    self.watchlist_path
                ),
                "code_count": len(valid_codes),
                "invalid_rows": invalid_codes[:10],
            },
        )

    @staticmethod
    def _check_kabu_station(
        payload: dict,
    ) -> ReadinessCheck:
        state = str(
            payload.get(
                "kabu_station_readiness",
                "unknown",
            )
        )
        connected = state == "connected"

        return ReadinessCheck(
            key="kabu_station",
            label="kabu Station",
            level=(
                ReadinessLevel.PASS
                if connected
                else ReadinessLevel.WARNING
            ),
            message=(
                "kabu Station readiness is connected."
                if connected
                else (
                    "kabu Station is not connected. "
                    f"state={state}"
                )
            ),
            required=True,
            details={
                "state": state,
            },
        )

    def _check_tailscale(
        self,
    ) -> ReadinessCheck:
        executable = shutil.which(
            "tailscale"
        )
        candidates = [
            Path(
                r"C:\Program Files\Tailscale\tailscale.exe"
            ),
        ]

        if executable is None:
            for candidate in candidates:
                if candidate.exists():
                    executable = str(candidate)
                    break

        if executable is None:
            return ReadinessCheck(
                key="tailscale",
                label="Tailscale",
                level=ReadinessLevel.WARNING,
                message="Tailscale CLI was not found.",
                required=False,
                details={},
            )

        try:
            completed = self.tailscale_runner(
                [
                    executable,
                    "ip",
                    "-4",
                ],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=3.0,
            )
        except (
            OSError,
            subprocess.TimeoutExpired,
        ) as error:
            return ReadinessCheck(
                key="tailscale",
                label="Tailscale",
                level=ReadinessLevel.WARNING,
                message=str(error),
                required=False,
                details={},
            )

        address = completed.stdout.strip()
        passed = (
            completed.returncode == 0
            and bool(address)
        )

        return ReadinessCheck(
            key="tailscale",
            label="Tailscale",
            level=(
                ReadinessLevel.PASS
                if passed
                else ReadinessLevel.WARNING
            ),
            message=(
                f"Tailscale is ready. address={address}"
                if passed
                else "Tailscale IPv4 is unavailable."
            ),
            required=False,
            details={
                "address": address or None,
                "exit_code": completed.returncode,
            },
        )

    def _check_storage(
        self,
    ) -> ReadinessCheck:
        usage = shutil.disk_usage(
            self.project_directory
        )
        passed = (
            usage.free
            >= self.minimum_free_bytes
        )

        return ReadinessCheck(
            key="storage",
            label="Storage",
            level=(
                ReadinessLevel.PASS
                if passed
                else ReadinessLevel.WARNING
            ),
            message=(
                "Storage free space is sufficient."
                if passed
                else "Storage free space is low."
            ),
            required=False,
            details={
                "free_bytes": usage.free,
                "total_bytes": usage.total,
                "minimum_free_bytes": (
                    self.minimum_free_bytes
                ),
            },
        )

    def _check_logs(
        self,
    ) -> ReadinessCheck:
        targets = (
            self.project_directory
            / "logs"
            / "service"
            / "katana_service.log",
            self.project_directory
            / "katana.log",
        )
        oversized = [
            {
                "path": str(path),
                "size_bytes": path.stat().st_size,
            }
            for path in targets
            if path.exists()
            and path.stat().st_size
            > self.maximum_log_bytes
        ]

        return ReadinessCheck(
            key="logs",
            label="Operational Logs",
            level=(
                ReadinessLevel.WARNING
                if oversized
                else ReadinessLevel.PASS
            ),
            message=(
                "One or more operational logs "
                "exceed the rotation threshold."
                if oversized
                else "Operational log sizes are normal."
            ),
            required=False,
            details={
                "oversized": oversized,
                "maximum_log_bytes": (
                    self.maximum_log_bytes
                ),
            },
        )

    def _current_time(self) -> datetime:
        value = self.now_provider()

        if value.tzinfo is None:
            raise ValueError(
                "現在日時にはタイムゾーンが必要です。"
            )

        return value.astimezone(timezone.utc)
