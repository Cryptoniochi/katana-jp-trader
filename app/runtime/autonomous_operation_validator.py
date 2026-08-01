"""Project KATANA自律運転構成を読み取り専用で検証する。"""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.runtime.autonomous_operation_models import (
    AutonomousCheckLevel,
    AutonomousOperationCheck,
    AutonomousOperationReport,
)


class AutonomousOperationValidator:
    """営業日前の自律運転構成を一括確認する。"""

    REQUIRED_COMPONENTS = {
        "dashboard": True,
        "daily_report_scheduler": True,
        "paper_trading_scheduler": True,
        "paper_trading": False,
    }

    def __init__(
        self,
        *,
        service_status_path: Path,
        paper_schedule_status_path: Path,
        daily_report_schedule_status_path: Path,
        watchlist_path: Path,
        database_path: Path,
        now_provider: Callable[[], datetime] | None = None,
        readiness_runner: Callable[..., subprocess.CompletedProcess] = (
            subprocess.run
        ),
    ) -> None:
        self.service_status_path = Path(
            service_status_path
        )
        self.paper_schedule_status_path = Path(
            paper_schedule_status_path
        )
        self.daily_report_schedule_status_path = Path(
            daily_report_schedule_status_path
        )
        self.watchlist_path = Path(watchlist_path)
        self.database_path = Path(database_path)
        self.now_provider = (
            now_provider
            if now_provider is not None
            else lambda: datetime.now(timezone.utc)
        )
        self.readiness_runner = readiness_runner

    def evaluate(
        self,
    ) -> AutonomousOperationReport:
        """自律運転準備状態を返す。"""

        checks = (
            self._check_service_status(),
            self._check_component_topology(),
            self._check_paper_schedule(),
            self._check_daily_report_schedule(),
            self._check_watchlist(),
            self._check_database(),
            self._check_production_readiness(),
        )

        failures = [
            check
            for check in checks
            if check.level is AutonomousCheckLevel.FAIL
        ]
        warnings = [
            check
            for check in checks
            if check.level is AutonomousCheckLevel.WARNING
        ]

        if failures:
            overall_state = "blocked"
        elif warnings:
            overall_state = "attention"
        else:
            overall_state = "ready"

        return AutonomousOperationReport(
            generated_at=self._current_time(),
            overall_state=overall_state,
            ready_for_next_business_day=not failures,
            checks=checks,
        )

    def _check_service_status(
        self,
    ) -> AutonomousOperationCheck:
        payload = self._read_json(
            self.service_status_path
        )

        if payload is None:
            return AutonomousOperationCheck(
                key="service_status",
                label="KATANA Service",
                level=AutonomousCheckLevel.FAIL,
                message=(
                    "Service status file is unavailable."
                ),
                details={
                    "path": str(
                        self.service_status_path
                    )
                },
            )

        state = str(
            payload.get(
                "service_state",
                "unknown",
            )
        )
        passed = state == "healthy"

        return AutonomousOperationCheck(
            key="service_status",
            label="KATANA Service",
            level=(
                AutonomousCheckLevel.PASS
                if passed
                else AutonomousCheckLevel.FAIL
            ),
            message=(
                "KATANA Service is healthy."
                if passed
                else f"KATANA Service state={state}"
            ),
            details={
                "service_state": state,
                "service_started_at": payload.get(
                    "service_started_at"
                ),
                "uptime_seconds": payload.get(
                    "uptime_seconds"
                ),
                "kabu_station_readiness": payload.get(
                    "kabu_station_readiness"
                ),
            },
        )

    def _check_component_topology(
        self,
    ) -> AutonomousOperationCheck:
        payload = self._read_json(
            self.service_status_path
        )

        if payload is None:
            return AutonomousOperationCheck(
                key="component_topology",
                label="Service Components",
                level=AutonomousCheckLevel.FAIL,
                message=(
                    "Service component topology "
                    "cannot be inspected."
                ),
                details={},
            )

        components = {
            str(component.get("name")): component
            for component in payload.get(
                "components",
                []
            )
            if isinstance(component, dict)
        }
        problems: list[str] = []

        for name, expected_enabled in (
            self.REQUIRED_COMPONENTS.items()
        ):
            component = components.get(name)

            if component is None:
                problems.append(
                    f"missing:{name}"
                )
                continue

            actual_enabled = bool(
                component.get(
                    "enabled",
                    False,
                )
            )

            if actual_enabled != expected_enabled:
                problems.append(
                    f"enabled:{name}={actual_enabled}"
                )

            if (
                expected_enabled
                and component.get("state") != "running"
            ):
                problems.append(
                    f"state:{name}="
                    f"{component.get('state')}"
                )

        return AutonomousOperationCheck(
            key="component_topology",
            label="Service Components",
            level=(
                AutonomousCheckLevel.FAIL
                if problems
                else AutonomousCheckLevel.PASS
            ),
            message=(
                "Service component topology is correct."
                if not problems
                else (
                    "Service component topology "
                    "has problems."
                )
            ),
            details={
                "problems": problems,
                "components": sorted(
                    components
                ),
            },
        )

    def _check_paper_schedule(
        self,
    ) -> AutonomousOperationCheck:
        payload = self._read_json(
            self.paper_schedule_status_path
        )

        if payload is None:
            return AutonomousOperationCheck(
                key="paper_schedule",
                label="Paper Trading Scheduler",
                level=AutonomousCheckLevel.FAIL,
                message=(
                    "Paper Trading schedule status "
                    "is unavailable."
                ),
                details={
                    "path": str(
                        self.paper_schedule_status_path
                    )
                },
            )

        enabled = bool(
            payload.get(
                "enabled",
                False,
            )
        )
        state = str(
            payload.get(
                "state",
                "unknown",
            )
        )
        acceptable_states = {
            "closed_day",
            "before_start",
            "running",
            "lunch_break",
            "completed",
            "failed",
        }
        passed = (
            enabled
            and state in acceptable_states
        )
        level = (
            AutonomousCheckLevel.WARNING
            if state == "failed"
            else (
                AutonomousCheckLevel.PASS
                if passed
                else AutonomousCheckLevel.FAIL
            )
        )

        return AutonomousOperationCheck(
            key="paper_schedule",
            label="Paper Trading Scheduler",
            level=level,
            message=(
                f"Paper Trading schedule state={state}"
            ),
            details={
                "enabled": enabled,
                "state": state,
                "business_day": payload.get(
                    "business_day"
                ),
                "next_action_at": payload.get(
                    "next_action_at"
                ),
                "message": payload.get(
                    "message"
                ),
            },
        )

    def _check_daily_report_schedule(
        self,
    ) -> AutonomousOperationCheck:
        payload = self._read_json(
            self.daily_report_schedule_status_path
        )

        if payload is None:
            return AutonomousOperationCheck(
                key="daily_report_schedule",
                label="Daily Report Scheduler",
                level=AutonomousCheckLevel.FAIL,
                message=(
                    "Daily Report schedule status "
                    "is unavailable."
                ),
                details={
                    "path": str(
                        self.daily_report_schedule_status_path
                    )
                },
            )

        enabled = bool(
            payload.get(
                "enabled",
                False,
            )
        )
        state = str(
            payload.get(
                "state",
                "unknown",
            )
        )
        level = (
            AutonomousCheckLevel.WARNING
            if state in {"failed", "retry_wait"}
            else (
                AutonomousCheckLevel.PASS
                if enabled
                else AutonomousCheckLevel.FAIL
            )
        )

        return AutonomousOperationCheck(
            key="daily_report_schedule",
            label="Daily Report Scheduler",
            level=level,
            message=(
                f"Daily Report schedule state={state}"
            ),
            details={
                "enabled": enabled,
                "state": state,
                "business_day": payload.get(
                    "business_day"
                ),
                "next_action_at": payload.get(
                    "next_action_at"
                ),
                "message": payload.get(
                    "message"
                ),
            },
        )

    def _check_watchlist(
        self,
    ) -> AutonomousOperationCheck:
        if not self.watchlist_path.exists():
            return AutonomousOperationCheck(
                key="watchlist",
                label="Watchlist",
                level=AutonomousCheckLevel.FAIL,
                message="Watchlist file does not exist.",
                details={
                    "path": str(
                        self.watchlist_path
                    )
                },
            )

        codes = [
            line.strip()
            for line in self.watchlist_path.read_text(
                encoding="utf-8-sig"
            ).splitlines()
            if line.strip().isdigit()
            and len(line.strip()) == 4
        ]
        unique_codes = tuple(
            dict.fromkeys(codes)
        )
        passed = (
            1 <= len(unique_codes) <= 50
        )

        return AutonomousOperationCheck(
            key="watchlist",
            label="Watchlist",
            level=(
                AutonomousCheckLevel.PASS
                if passed
                else AutonomousCheckLevel.FAIL
            ),
            message=(
                f"Watchlist codes={len(unique_codes)}"
            ),
            details={
                "path": str(
                    self.watchlist_path
                ),
                "code_count": len(unique_codes),
                "maximum": 50,
            },
        )

    def _check_database(
        self,
    ) -> AutonomousOperationCheck:
        exists = self.database_path.exists()

        return AutonomousOperationCheck(
            key="database",
            label="Database",
            level=(
                AutonomousCheckLevel.PASS
                if exists
                else AutonomousCheckLevel.FAIL
            ),
            message=(
                "Database file exists."
                if exists
                else "Database file does not exist."
            ),
            details={
                "path": str(
                    self.database_path
                ),
                "size_bytes": (
                    self.database_path.stat().st_size
                    if exists
                    else None
                ),
            },
        )

    def _check_production_readiness(
        self,
    ) -> AutonomousOperationCheck:
        completed = self.readiness_runner(
            [
                sys.executable,
                "-m",
                "app.run_paper_trading",
                "--check",
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120.0,
        )
        passed = completed.returncode == 0

        return AutonomousOperationCheck(
            key="production_readiness",
            label="Production Readiness",
            level=(
                AutonomousCheckLevel.PASS
                if passed
                else AutonomousCheckLevel.FAIL
            ),
            message=(
                "Production Readiness is READY."
                if passed
                else (
                    "Production Readiness is NOT READY."
                )
            ),
            details={
                "exit_code": completed.returncode,
                "stdout_tail": completed.stdout[-2000:],
                "stderr_tail": completed.stderr[-2000:],
            },
        )

    @staticmethod
    def _read_json(
        path: Path,
    ) -> dict[str, Any] | None:
        if not path.exists():
            return None

        try:
            payload = json.loads(
                path.read_text(
                    encoding="utf-8"
                )
            )
        except (
            OSError,
            UnicodeError,
            json.JSONDecodeError,
        ):
            return None

        return (
            payload
            if isinstance(payload, dict)
            else None
        )

    def _current_time(self) -> datetime:
        value = self.now_provider()

        if value.tzinfo is None:
            raise ValueError(
                "現在日時にはタイムゾーンが必要です。"
            )

        return value.astimezone(timezone.utc)
