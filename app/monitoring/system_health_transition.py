"""総合ヘルス状態の変化を検出する。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.monitoring.system_health_models import (
    SystemHealthReport,
    SystemHealthStatus,
)


class SystemHealthTransitionType(StrEnum):
    """総合ヘルス状態変化の種類。"""

    INITIAL = "initial"
    DEGRADED = "degraded"
    RECOVERED = "recovered"
    CHANGED = "changed"


@dataclass(frozen=True, slots=True)
class SystemHealthTransition:
    """通知・ログ対象となる総合ヘルス状態変化。"""

    transition_type: SystemHealthTransitionType
    detected_at: datetime
    previous_status: SystemHealthStatus | None
    current_status: SystemHealthStatus
    previous_report: SystemHealthReport | None
    current_report: SystemHealthReport
    check_number: int

    def __post_init__(self) -> None:
        """状態変化の整合性を検証する。"""

        if self.detected_at.tzinfo is None:
            raise ValueError(
                "状態変化検出日時にはタイムゾーンが必要です。"
            )

        if self.check_number <= 0:
            raise ValueError(
                "チェック番号は0より大きい必要があります。"
            )

        if (
            self.transition_type
            is SystemHealthTransitionType.INITIAL
            and self.previous_status is not None
        ):
            raise ValueError(
                "初回状態には直前状態を設定できません。"
            )

        if (
            self.transition_type
            is not SystemHealthTransitionType.INITIAL
            and self.previous_status is None
        ):
            raise ValueError(
                "初回以外の状態変化には直前状態が必要です。"
            )

    @property
    def is_degradation(self) -> bool:
        """状態悪化か返す。"""

        return (
            self.transition_type
            is SystemHealthTransitionType.DEGRADED
        )

    @property
    def is_recovery(self) -> bool:
        """状態改善か返す。"""

        return (
            self.transition_type
            is SystemHealthTransitionType.RECOVERED
        )

    @property
    def message(self) -> str:
        """状態変化を表すメッセージを返す。"""

        previous = (
            self.previous_status.value
            if self.previous_status is not None
            else "none"
        )

        reason_text = (
            " | ".join(self.current_report.reasons)
            if self.current_report.reasons
            else "no issues"
        )

        return (
            "システムヘルス状態変化: "
            f"type={self.transition_type.value} "
            f"previous={previous} "
            f"current={self.current_status.value} "
            f"check_number={self.check_number} "
            f"reasons={reason_text}"
        )


class SystemHealthTransitionDetector:
    """連続する総合ヘルス結果から状態変化を検出する。"""

    STATUS_SEVERITY = {
        SystemHealthStatus.HEALTHY: 0,
        SystemHealthStatus.WARNING: 1,
        SystemHealthStatus.DEGRADED: 2,
        SystemHealthStatus.CRITICAL: 3,
    }

    def __init__(
        self,
        *,
        notify_initial_state: bool = True,
    ) -> None:
        """初回状態を通知対象にするか設定する。"""

        self.notify_initial_state = notify_initial_state
        self._previous_report: SystemHealthReport | None = None
        self._previous_check_number: int | None = None

    @property
    def previous_report(self) -> SystemHealthReport | None:
        """最後に受け取った総合ヘルス結果を返す。"""

        return self._previous_report

    def detect(
        self,
        report: SystemHealthReport,
        *,
        check_number: int,
    ) -> SystemHealthTransition | None:
        """総合ヘルス結果を受け取り状態変化を返す。"""

        if check_number <= 0:
            raise ValueError(
                "チェック番号は0より大きい必要があります。"
            )

        if (
            self._previous_check_number is not None
            and check_number <= self._previous_check_number
        ):
            raise ValueError(
                "チェック番号は前回より大きい必要があります。"
            )

        previous = self._previous_report

        if (
            previous is not None
            and report.checked_at < previous.checked_at
        ):
            raise ValueError(
                "確認日時は前回以後である必要があります。"
            )

        self._previous_report = report
        self._previous_check_number = check_number

        if previous is None:
            if not self.notify_initial_state:
                return None

            return SystemHealthTransition(
                transition_type=(
                    SystemHealthTransitionType.INITIAL
                ),
                detected_at=report.checked_at,
                previous_status=None,
                current_status=report.status,
                previous_report=None,
                current_report=report,
                check_number=check_number,
            )

        if previous.status is report.status:
            return None

        previous_severity = self.STATUS_SEVERITY[
            previous.status
        ]
        current_severity = self.STATUS_SEVERITY[
            report.status
        ]

        if current_severity > previous_severity:
            transition_type = (
                SystemHealthTransitionType.DEGRADED
            )
        elif current_severity < previous_severity:
            transition_type = (
                SystemHealthTransitionType.RECOVERED
            )
        else:
            transition_type = (
                SystemHealthTransitionType.CHANGED
            )

        return SystemHealthTransition(
            transition_type=transition_type,
            detected_at=report.checked_at,
            previous_status=previous.status,
            current_status=report.status,
            previous_report=previous,
            current_report=report,
            check_number=check_number,
        )

    def reset(self) -> None:
        """保存済み状態を削除する。"""

        self._previous_report = None
        self._previous_check_number = None
