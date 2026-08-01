"""Morning Pre-Flight通知本文を生成する。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class MorningPreflightNotificationContent:
    """通知Gatewayへ渡すMorning Check内容。"""

    title: str
    body: str
    metadata: dict[str, Any]


class MorningPreflightNotificationFormatter:
    """自律運転検証PayloadをLINE・Discord向け本文へ変換する。"""

    def format(
        self,
        payload: dict[str, Any],
    ) -> MorningPreflightNotificationContent:
        """Morning Pre-Flight通知を生成する。"""

        checks = [
            check
            for check in payload.get("checks", [])
            if isinstance(check, dict)
        ]
        overall_state = str(
            payload.get(
                "overall_state",
                "unknown",
            )
        )
        ready = bool(
            payload.get(
                "ready_for_next_business_day",
                False,
            )
        )

        body_lines = [
            "━━━━━━━━━━━━━━━━━━",
            "Project KATANA",
            "Morning Pre-Flight",
            "━━━━━━━━━━━━━━━━━━",
            "",
        ]

        for check in checks:
            level = str(
                check.get(
                    "level",
                    "unknown",
                )
            )
            marker = {
                "pass": "OK",
                "warning": "WARN",
                "fail": "NG",
            }.get(
                level,
                "?",
            )
            body_lines.append(
                f"[{marker}] "
                f"{check.get('label', check.get('key', 'Unknown'))}"
            )

        body_lines.extend(
            [
                "",
                "Overall",
                overall_state.upper(),
                "",
                "Trading",
                (
                    "READY FOR TRADING"
                    if ready
                    else "NOT READY"
                ),
            ]
        )

        failed_checks = [
            check
            for check in checks
            if check.get("level") == "fail"
        ]

        if failed_checks:
            body_lines.extend(
                [
                    "",
                    "Reasons",
                ]
            )
            body_lines.extend(
                f"- {check.get('label', check.get('key', 'Unknown'))}: "
                f"{check.get('message', '')}"
                for check in failed_checks
            )

        return MorningPreflightNotificationContent(
            title=(
                "Project KATANA Morning Check "
                f"{overall_state.upper()}"
            ),
            body="\n".join(body_lines),
            metadata={
                "event_type": "morning_preflight",
                "overall_state": overall_state,
                "ready_for_next_business_day": ready,
                "failed_check_count": len(
                    failed_checks
                ),
                "warning_check_count": len(
                    [
                        check
                        for check in checks
                        if check.get("level")
                        == "warning"
                    ]
                ),
            },
        )
