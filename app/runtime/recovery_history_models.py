"""Recovery履歴の共通データモデル。"""

from dataclasses import dataclass
from enum import StrEnum

from app.runtime.recovery_models import RecoveryResult


class RecoveryComponent(StrEnum):
    """復旧対象コンポーネント。"""

    BROKER = "broker"
    RUNTIME = "runtime"


@dataclass(frozen=True, slots=True)
class RecoveryHistoryEntry:
    """保存対象となる1件のRecovery履歴。"""

    component: RecoveryComponent
    result: RecoveryResult

    @property
    def recovery_name(self) -> str:
        """復旧処理名を返す。"""

        return self.result.recovery_name

    @property
    def started_at(self):
        """復旧処理の開始日時を返す。"""

        return self.result.started_at

    @property
    def completed_at(self):
        """復旧処理の完了日時を返す。"""

        return self.result.completed_at

    @property
    def attempt_count(self) -> int:
        """復旧試行回数を返す。"""

        return self.result.attempt_count

    @property
    def success_count(self) -> int:
        """成功した復旧試行数を返す。"""

        return sum(
            1
            for attempt in self.result.attempts
            if attempt.successful
        )

    @property
    def failure_count(self) -> int:
        """失敗した復旧試行数を返す。"""

        return sum(
            1
            for attempt in self.result.attempts
            if not attempt.successful
        )