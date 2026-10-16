"""High Breakout候補を営業日引け後に翌営業日向けに自動生成する。"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime, time as clock_time
from pathlib import Path
from zoneinfo import ZoneInfo

from app.market.market_calendar import TokyoMarketCalendar
from app.run_high_breakout_operation import execute_operation


JST = ZoneInfo("Asia/Tokyo")
DEFAULT_STATUS_PATH = Path(
    "reports/high_breakout/high_breakout_scheduler_status.json"
)


@dataclass(frozen=True, slots=True)
class SchedulerStatus:
    generated_at: str
    trading_date: str
    target_trading_date: str | None
    state: str
    business_day: bool
    enabled: bool
    next_action_at: str | None
    last_attempt_at: str | None
    operation_exit_code: int | None
    daily_bar_count: int | None
    candidate_count: int | None
    message: str
    settings: dict[str, object]


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "営業日15:38にHigh Breakoutの日足生成・候補抽出を"
            "翌JPX営業日向けに自動実行します。"
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
        "--output-directory",
        type=Path,
        default=Path("reports/high_breakout"),
    )
    parser.add_argument("--run-at", default="15:38")
    parser.add_argument(
        "--poll-interval-seconds",
        type=float,
        default=30.0,
    )
    parser.add_argument(
        "--source-interval-minutes",
        type=int,
        default=5,
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
        "--status-path",
        type=Path,
        default=DEFAULT_STATUS_PATH,
    )
    parser.add_argument("--enable", action="store_true")
    parser.add_argument("--once", action="store_true")
    return parser


def _parse_run_at(value: str) -> clock_time:
    try:
        hour_text, minute_text = value.split(":", 1)
        return clock_time(
            hour=int(hour_text),
            minute=int(minute_text),
        )
    except (TypeError, ValueError) as error:
        raise ValueError("--run-at must be HH:MM") from error


def _scheduled_at(
    target_date,
    run_at: clock_time,
) -> datetime:
    return datetime(
        target_date.year,
        target_date.month,
        target_date.day,
        run_at.hour,
        run_at.minute,
        tzinfo=JST,
    )


def _write_status(
    path: Path,
    status: SchedulerStatus,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(
            asdict(status),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    temporary.replace(path)


def _next_scheduled_run(
    now: datetime,
    run_at: clock_time,
    calendar: TokyoMarketCalendar,
) -> datetime:
    today = now.date()
    today_scheduled = _scheduled_at(today, run_at)

    if (
        calendar.is_business_day(today)
        and now < today_scheduled
    ):
        return today_scheduled

    next_date = calendar.next_business_day(today)
    return _scheduled_at(next_date, run_at)


def _execute(
    parsed: argparse.Namespace,
    *,
    source_trading_date,
    calendar: TokyoMarketCalendar,
) -> tuple[int, int, int, object]:
    target_trading_date = calendar.next_business_day(
        source_trading_date
    )

    try:
        result = execute_operation(
            database_path=parsed.database_path,
            watchlist_path=parsed.watchlist_path,
            output_directory=parsed.output_directory,
            source_interval_minutes=(
                parsed.source_interval_minutes
            ),
            codes=(),
            minimum_volume_ratio=(
                parsed.minimum_volume_ratio
            ),
            minimum_turnover=parsed.minimum_turnover,
            target_trading_date=target_trading_date,
            start_paper_trading=False,
            paper_trading_dry_run=False,
        )
    except Exception as error:
        print(
            "High Breakout scheduled operation failed: "
            f"{type(error).__name__}: {error}"
        )
        return 1, 0, 0, target_trading_date

    exit_code = 0 if result.successful else 1
    return (
        exit_code,
        result.daily_bar_count,
        result.candidate_count,
        target_trading_date,
    )


def run(arguments: list[str] | None = None) -> int:
    parsed = build_argument_parser().parse_args(arguments)
    run_at = _parse_run_at(parsed.run_at)
    calendar = TokyoMarketCalendar()

    if parsed.poll_interval_seconds <= 0:
        raise ValueError(
            "--poll-interval-seconds must be > 0"
        )

    if parsed.once:
        now = datetime.now(JST)
        source_date = now.date()
        exit_code, daily_count, candidate_count, target_date = (
            _execute(
                parsed,
                source_trading_date=source_date,
                calendar=calendar,
            )
        )
        finished = datetime.now(JST)
        _write_status(
            parsed.status_path,
            SchedulerStatus(
                generated_at=finished.isoformat(),
                trading_date=source_date.isoformat(),
                target_trading_date=target_date.isoformat(),
                state=(
                    "completed"
                    if exit_code == 0
                    else "failed"
                ),
                business_day=calendar.is_business_day(
                    source_date
                ),
                enabled=parsed.enable,
                next_action_at=None,
                last_attempt_at=now.isoformat(),
                operation_exit_code=exit_code,
                daily_bar_count=daily_count,
                candidate_count=candidate_count,
                message=(
                    "One-shot High Breakout operation "
                    "completed for next JPX business day."
                ),
                settings={
                    "run_at": parsed.run_at,
                    "source_interval_minutes": (
                        parsed.source_interval_minutes
                    ),
                    "minimum_volume_ratio": (
                        parsed.minimum_volume_ratio
                    ),
                    "minimum_turnover": (
                        parsed.minimum_turnover
                    ),
                },
            ),
        )
        return exit_code

    last_run_date = None

    while True:
        now = datetime.now(JST)
        today = now.date()
        business_day = calendar.is_business_day(today)
        scheduled = _scheduled_at(today, run_at)

        if not parsed.enable:
            _write_status(
                parsed.status_path,
                SchedulerStatus(
                    generated_at=now.isoformat(),
                    trading_date=today.isoformat(),
                    target_trading_date=None,
                    state="disabled",
                    business_day=business_day,
                    enabled=False,
                    next_action_at=None,
                    last_attempt_at=None,
                    operation_exit_code=None,
                    daily_bar_count=None,
                    candidate_count=None,
                    message=(
                        "High Breakout schedule is disabled."
                    ),
                    settings={"run_at": parsed.run_at},
                ),
            )
            time.sleep(parsed.poll_interval_seconds)
            continue

        if (
            business_day
            and now >= scheduled
            and last_run_date != today
        ):
            attempted_at = now
            (
                exit_code,
                daily_count,
                candidate_count,
                target_date,
            ) = _execute(
                parsed,
                source_trading_date=today,
                calendar=calendar,
            )
            last_run_date = today
            finished = datetime.now(JST)

            _write_status(
                parsed.status_path,
                SchedulerStatus(
                    generated_at=finished.isoformat(),
                    trading_date=today.isoformat(),
                    target_trading_date=(
                        target_date.isoformat()
                    ),
                    state=(
                        "completed"
                        if exit_code == 0
                        else "failed"
                    ),
                    business_day=True,
                    enabled=True,
                    next_action_at=_next_scheduled_run(
                        finished,
                        run_at,
                        calendar,
                    ).isoformat(),
                    last_attempt_at=(
                        attempted_at.isoformat()
                    ),
                    operation_exit_code=exit_code,
                    daily_bar_count=daily_count,
                    candidate_count=candidate_count,
                    message=(
                        "High Breakout candidates generated "
                        "for next JPX business day."
                        if exit_code == 0
                        else
                        "High Breakout candidate generation "
                        "failed."
                    ),
                    settings={
                        "run_at": parsed.run_at,
                        "source_interval_minutes": (
                            parsed.source_interval_minutes
                        ),
                        "minimum_volume_ratio": (
                            parsed.minimum_volume_ratio
                        ),
                        "minimum_turnover": (
                            parsed.minimum_turnover
                        ),
                    },
                ),
            )
        else:
            next_action = _next_scheduled_run(
                now,
                run_at,
                calendar,
            )
            _write_status(
                parsed.status_path,
                SchedulerStatus(
                    generated_at=now.isoformat(),
                    trading_date=today.isoformat(),
                    target_trading_date=None,
                    state="waiting",
                    business_day=business_day,
                    enabled=True,
                    next_action_at=next_action.isoformat(),
                    last_attempt_at=None,
                    operation_exit_code=None,
                    daily_bar_count=None,
                    candidate_count=None,
                    message=(
                        "Waiting for scheduled "
                        "High Breakout screening."
                    ),
                    settings={"run_at": parsed.run_at},
                ),
            )

        time.sleep(parsed.poll_interval_seconds)


if __name__ == "__main__":
    raise SystemExit(run())
