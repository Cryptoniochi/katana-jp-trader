"""Recovery Dashboardで使用する回復処理サマリーモデル。"""

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum


class RecoveryStatus(StrEnum):
    """回復処理全体の状態。"""

    NORMAL = "normal"
    RECOVERING = "recovering"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class RecoverySummary:
    """Broker・Runtime回復処理の集計情報。

    Dashboard、Web API、Daily Reportから共通利用することを想定した
    読み取り専用のデータモデル。
    """

    broker_attempts: int = 0
    broker_successes: int = 0
    broker_failures: int = 0
    last_broker_recovery: datetime | None = None

    runtime_attempts: int = 0
    runtime_successes: int = 0
    runtime_failures: int = 0
    last_runtime_recovery: datetime | None = None

    recovery_status: RecoveryStatus = RecoveryStatus.NORMAL
    generated_at: datetime | None = None

    def __post_init__(self) -> None:
        """各フィールドの整合性を検証し、生成日時を補完する。"""

        self._validate_non_negative_counts()
        self._validate_attempt_counts()
        self._validate_datetime(
            name="last_broker_recovery",
            value=self.last_broker_recovery,
        )
        self._validate_datetime(
            name="last_runtime_recovery",
            value=self.last_runtime_recovery,
        )

        if self.generated_at is None:
            object.__setattr__(
                self,
                "generated_at",
                datetime.now(timezone.utc),
            )
        else:
            self._validate_datetime(
                name="generated_at",
                value=self.generated_at,
            )

    @property
    def total_attempts(self) -> int:
        """BrokerとRuntimeを合計した回復試行回数を返す。"""

        return self.broker_attempts + self.runtime_attempts

    @property
    def total_successes(self) -> int:
        """BrokerとRuntimeを合計した回復成功回数を返す。"""

        return self.broker_successes + self.runtime_successes

    @property
    def total_failures(self) -> int:
        """BrokerとRuntimeを合計した回復失敗回数を返す。"""

        return self.broker_failures + self.runtime_failures

    def success_rate(self) -> float:
        """回復処理全体の成功率をパーセントで返す。

        試行回数が0件の場合は、失敗が発生していないため100.0を返す。
        戻り値は小数第2位までに丸める。
        """

        if self.total_attempts == 0:
            return 100.0

        return round(
            self.total_successes / self.total_attempts * 100.0,
            2,
        )

    def has_failure(self) -> bool:
        """回復失敗が1件以上存在するか返す。"""

        return self.total_failures > 0

    def is_healthy(self) -> bool:
        """Recovery全体が正常な状態か返す。"""

        return (
            self.recovery_status is RecoveryStatus.NORMAL
            and not self.has_failure()
        )

    def to_dict(self) -> dict[str, object]:
        """JSONへ変換可能な辞書形式で返す。"""

        return {
            "broker": {
                "attempts": self.broker_attempts,
                "successes": self.broker_successes,
                "failures": self.broker_failures,
                "last_recovery": self._format_datetime(
                    self.last_broker_recovery
                ),
            },
            "runtime": {
                "attempts": self.runtime_attempts,
                "successes": self.runtime_successes,
                "failures": self.runtime_failures,
                "last_recovery": self._format_datetime(
                    self.last_runtime_recovery
                ),
            },
            "aggregate": {
                "total_attempts": self.total_attempts,
                "total_successes": self.total_successes,
                "total_failures": self.total_failures,
                "success_rate": self.success_rate(),
            },
            "recovery_status": self.recovery_status.value,
            "has_failure": self.has_failure(),
            "is_healthy": self.is_healthy(),
            "generated_at": self._format_datetime(self.generated_at),
        }

    def _validate_non_negative_counts(self) -> None:
        """回数フィールドが0以上であることを検証する。"""

        count_fields = {
            "broker_attempts": self.broker_attempts,
            "broker_successes": self.broker_successes,
            "broker_failures": self.broker_failures,
            "runtime_attempts": self.runtime_attempts,
            "runtime_successes": self.runtime_successes,
            "runtime_failures": self.runtime_failures,
        }

        for name, value in count_fields.items():
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an int")

            if value < 0:
                raise ValueError(f"{name} must be greater than or equal to 0")

    def _validate_attempt_counts(self) -> None:
        """成功・失敗件数が試行回数と一致することを検証する。"""

        broker_results = self.broker_successes + self.broker_failures
        if broker_results != self.broker_attempts:
            raise ValueError(
                "broker_attempts must equal "
                "broker_successes + broker_failures"
            )

        runtime_results = self.runtime_successes + self.runtime_failures
        if runtime_results != self.runtime_attempts:
            raise ValueError(
                "runtime_attempts must equal "
                "runtime_successes + runtime_failures"
            )

    @staticmethod
    def _validate_datetime(
        *,
        name: str,
        value: datetime | None,
    ) -> None:
        """日時がtimezone-awareであることを検証する。"""

        if value is None:
            return

        if not isinstance(value, datetime):
            raise TypeError(f"{name} must be a datetime or None")

        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(f"{name} must be timezone-aware")

    @staticmethod
    def _format_datetime(value: datetime | None) -> str | None:
        """日時をISO 8601形式へ変換する。"""

        if value is None:
            return None

        return value.isoformat()