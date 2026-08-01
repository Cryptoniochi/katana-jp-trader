"""Project KATANA Daily Report通知CLI。"""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
from typing import Sequence

from app.dashboard.daily_report_reader import (
    DailyReportReader,
)
from app.notifications.daily_report_formatter import (
    DailyReportNotificationFormatter,
)
from app.notifications.daily_report_notification_service import (
    DailyReportNotificationService,
)
from app.notifications.notification_composition import (
    NotificationComposition,
)
from app.notifications.notification_rule_models import (
    NotificationRulePolicy,
)
from app.settings import ROOT_DIR, Settings


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Daily Trading ReportをLINE・Discordへ送信します。"
        )
    )
    parser.add_argument(
        "--report-directory",
        type=Path,
        default=Path("reports/daily"),
    )
    parser.add_argument(
        "--report-date",
        type=date.fromisoformat,
        default=None,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "通知せず、送信予定本文だけを表示します。"
        ),
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
    reader = DailyReportReader(
        parsed.report_directory
    )
    payload = (
        reader.read_for_date(
            parsed.report_date
        )
        if parsed.report_date is not None
        else reader.read_latest()
    )

    if parsed.dry_run:
        content = (
            DailyReportNotificationFormatter()
            .format(payload)
        )
        print(content.title)
        print()
        print(content.body)
        return 0

    settings = Settings.from_environment(
        env_file=ROOT_DIR / ".env"
    )
    provisional = NotificationComposition.create(
        settings=settings.notifications,
        require_channel=False,
    )

    if not provisional.channels:
        print(
            "Daily Report notification was not sent: "
            "no LINE or Discord channel is configured."
        )
        return 2

    channel_names = (
        provisional.channel_names
    )
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
    service = DailyReportNotificationService(
        reader=reader,
        gateway=bundle.gateway,
    )
    result = (
        service.send_for_date(
            parsed.report_date,
            continue_on_error=(
                not parsed.fail_fast
            ),
        )
        if parsed.report_date is not None
        else service.send_latest(
            continue_on_error=(
                not parsed.fail_fast
            )
        )
    )

    print("Daily Report notification completed.")
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
        "suppressed="
        f"{result.gateway_result.was_suppressed}"
    )

    if result.gateway_result.was_suppressed:
        reasons = (
            result.gateway_result
            .routing_result
            .routing
            .reasons
        )
        print(
            "suppression_reasons="
            + ",".join(
                reason.value
                for reason in reasons
            )
        )

    return (
        0
        if result.failed_count == 0
        and result.delivered_count > 0
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(run())
