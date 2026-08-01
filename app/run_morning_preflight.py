"""Project KATANA Morning Pre-Flight CLI。"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from app.notifications.morning_preflight_formatter import (
    MorningPreflightNotificationFormatter,
)
from app.notifications.morning_preflight_notification_service import (
    MorningPreflightNotificationService,
)
from app.notifications.notification_composition import (
    NotificationComposition,
)
from app.notifications.notification_rule_models import (
    NotificationRulePolicy,
)
from app.runtime.autonomous_operation_validator import (
    AutonomousOperationValidator,
)
from app.settings import ROOT_DIR, Settings


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "自律運転検証を実行し、"
            "LINE・DiscordへMorning Checkを送信します。"
        )
    )
    parser.add_argument(
        "--service-status-path",
        type=Path,
        default=Path(
            "reports/service/katana_service_status.json"
        ),
    )
    parser.add_argument(
        "--paper-schedule-status-path",
        type=Path,
        default=Path(
            "reports/service/paper_trading_schedule.json"
        ),
    )
    parser.add_argument(
        "--daily-report-schedule-status-path",
        type=Path,
        default=Path(
            "reports/service/daily_report_schedule.json"
        ),
    )
    parser.add_argument(
        "--watchlist-path",
        type=Path,
        default=Path("watchlist.txt"),
    )
    parser.add_argument(
        "--database-path",
        type=Path,
        default=Path("data/katana.db"),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
    )
    return parser


def run(
    arguments: Sequence[str] | None = None,
) -> int:
    parsed = build_argument_parser().parse_args(
        arguments
    )
    validator = AutonomousOperationValidator(
        service_status_path=(
            parsed.service_status_path
        ),
        paper_schedule_status_path=(
            parsed.paper_schedule_status_path
        ),
        daily_report_schedule_status_path=(
            parsed.daily_report_schedule_status_path
        ),
        watchlist_path=parsed.watchlist_path,
        database_path=parsed.database_path,
    )

    if parsed.dry_run:
        payload = validator.evaluate().to_dict()
        content = (
            MorningPreflightNotificationFormatter()
            .format(payload)
        )
        print(content.title)
        print()
        print(content.body)
        return (
            0
            if payload[
                "ready_for_next_business_day"
            ]
            else 1
        )

    settings = Settings.from_environment(
        env_file=ROOT_DIR / ".env"
    )
    provisional = NotificationComposition.create(
        settings=settings.notifications,
        require_channel=False,
    )

    if not provisional.channels:
        print(
            "Morning Pre-Flight was not sent: "
            "no LINE or Discord channel is configured."
        )
        return 2

    channel_names = provisional.channel_names
    policy = NotificationRulePolicy(
        info_channels=channel_names,
        warning_channels=channel_names,
        error_channels=channel_names,
        critical_channels=channel_names,
        quiet_hours_suppressed_severities=frozenset(),
        duplicate_cooldown_seconds=0,
    )
    bundle = NotificationComposition.create(
        settings=settings.notifications,
        policy=policy,
        require_channel=True,
    )
    result = MorningPreflightNotificationService(
        validator=validator,
        gateway=bundle.gateway,
    ).send(
        continue_on_error=(
            not parsed.fail_fast
        )
    )

    print("Morning Pre-Flight completed.")
    print(
        f"channels={','.join(bundle.channel_names)}"
    )
    print(
        f"delivered_count={result.delivered_count}"
    )
    print(
        f"failed_count={result.failed_count}"
    )
    print(
        "ready_for_next_business_day="
        f"{result.payload['ready_for_next_business_day']}"
    )

    return (
        0
        if result.failed_count == 0
        and result.delivered_count > 0
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(run())
