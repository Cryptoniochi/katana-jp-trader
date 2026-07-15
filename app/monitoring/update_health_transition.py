"""自動更新ヘルスチェックの状態変化を検出する。"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.monitoring.update_health_monitor import (
    UpdateHealthMonitorEvent,
)
from app.monitoring.update_health_service import (
    UpdateHealthReport,
    UpdateHealthStatus,
)


class UpdateHealthTransitionType(StrEnum):
    """ヘルスチェック状態変化の種類。"""

    INITIAL = "initial"
    DEGRADED = "degraded"
    RECOVERED = "recovered"
    CHANGED = "changed"


@dataclass(frozen=True, slots=True)
class UpdateHealthTransition:
    """通知対象となるヘルスチェック状態変化。"""

    transition_type: UpdateHealthTransitionType
    detected_at: datetime

    previous_status: UpdateHealthStatus | None
    current_status: UpdateHealthStatus

    previous_report: UpdateHealthReport | None
    current_report: UpdateHealthReport

    check_number: int

    @property
    def is_initial(self) -> bool:
        """初回状態通知か返す。"""

        return (
            self.transition_type
            is UpdateHealthTransitionType.INITIAL
        )

    @property
    def is_recovery(self) -> bool:
        """状態改善または正常復旧か返す。"""

        return (
            self.transition_type
            is UpdateHealthTransitionType.RECOVERED
        )

    @property
    def is_degradation(self) -> bool:
        """状態悪化か返す。"""

        return (
            self.transition_type
            is UpdateHealthTransitionType.DEGRADED
        )

    @property
    def message(self) -> str:
        """状態変化を表す通知用メッセージを返す。"""

        previous_status = (
            self.previous_status.value
            if self.previous_status is not None
            else "none"
        )

        return (
            "自動更新ヘルス状態変化: "
            f"type={self.transition_type.value} "
            f"previous={previous_status} "
            f"current={self.current_status.value} "
            f"check_number={self.check_number} "
            f"reason={self.current_report.reason}"
        )


class UpdateHealthTransitionDetector:
    """連続するヘルスチェック結果から状態変化を検出する。"""

    STATUS_SEVERITY = {
        UpdateHealthStatus.HEALTHY: 0,
        UpdateHealthStatus.WARNING: 1,
        UpdateHealthStatus.ERROR: 2,
    }

    def __init__(
        self,
        *,
        notify_initial_state: bool = True,
    ) -> None:
        """初回状態を通知対象にするか設定する。"""

        self.notify_initial_state = notify_initial_state

        self._previous_event: (
            UpdateHealthMonitorEvent | None
        ) = None

    @property
    def previous_event(
        self,
    ) -> UpdateHealthMonitorEvent | None:
        """最後に受け取った監視イベントを返す。"""

        return self._previous_event

    @property
    def previous_status(
        self,
    ) -> UpdateHealthStatus | None:
        """最後に受け取った状態を返す。"""

        if self._previous_event is None:
            return None

        return self._previous_event.status

    def detect(
        self,
        event: UpdateHealthMonitorEvent,
    ) -> UpdateHealthTransition | None:
        """監視イベントを受け取り、通知対象の変化を返す。"""

        previous_event = self._previous_event

        self._validate_event_order(
            previous_event=previous_event,
            current_event=event,
        )

        self._previous_event = event

        if previous_event is None:
            if not self.notify_initial_state:
                return None

            return UpdateHealthTransition(
                transition_type=(
                    UpdateHealthTransitionType.INITIAL
                ),
                detected_at=event.checked_at,
                previous_status=None,
                current_status=event.status,
                previous_report=None,
                current_report=event.report,
                check_number=event.check_number,
            )

        if previous_event.status is event.status:
            return None

        transition_type = (
            self._resolve_transition_type(
                previous_status=previous_event.status,
                current_status=event.status,
            )
        )

        return UpdateHealthTransition(
            transition_type=transition_type,
            detected_at=event.checked_at,
            previous_status=previous_event.status,
            current_status=event.status,
            previous_report=previous_event.report,
            current_report=event.report,
            check_number=event.check_number,
        )

    def reset(self) -> None:
        """保存済みの直前状態を削除する。"""

        self._previous_event = None

    @classmethod
    def _resolve_transition_type(
        cls,
        *,
        previous_status: UpdateHealthStatus,
        current_status: UpdateHealthStatus,
    ) -> UpdateHealthTransitionType:
        """状態の重大度から変化種類を決定する。"""

        previous_severity = cls.STATUS_SEVERITY[
            previous_status
        ]
        current_severity = cls.STATUS_SEVERITY[
            current_status
        ]

        if current_severity > previous_severity:
            return UpdateHealthTransitionType.DEGRADED

        if current_severity < previous_severity:
            return UpdateHealthTransitionType.RECOVERED

        return UpdateHealthTransitionType.CHANGED

    @staticmethod
    def _validate_event_order(
        *,
        previous_event: UpdateHealthMonitorEvent | None,
        current_event: UpdateHealthMonitorEvent,
    ) -> None:
        """監視イベントの順序を検証する。"""

        if current_event.check_number <= 0:
            raise ValueError(
                "チェック番号は0より大きい必要があります。"
            )

        if previous_event is None:
            return

        if (
            current_event.check_number
            <= previous_event.check_number
        ):
            raise ValueError(
                "監視イベントのチェック番号は"
                "前回より大きい必要があります。"
            )

        if (
            current_event.checked_at
            < previous_event.checked_at
        ):
            raise ValueError(
                "監視イベントの確認日時は"
                "前回以後である必要があります。"
            )