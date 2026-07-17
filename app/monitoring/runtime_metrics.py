"""Project KATANAのランタイム運用メトリクスモデル。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class RuntimeMetricName(StrEnum):
    """収集対象のランタイムメトリクス。"""

    DOMAIN_EVENT_COUNT = "domain_event_count"
    SIGNAL_COUNT = "signal_count"
    RISK_ASSESSMENT_COUNT = "risk_assessment_count"
    ORDER_CREATED_COUNT = "order_created_count"
    ORDER_UPDATED_COUNT = "order_updated_count"
    EXECUTION_RECORDED_COUNT = "execution_recorded_count"
    PORTFOLIO_UPDATED_COUNT = "portfolio_updated_count"
    RECOVERY_COMPLETED_COUNT = "recovery_completed_count"
    ERROR_OCCURRED_COUNT = "error_occurred_count"
    NOTIFICATION_DELIVERED_COUNT = "notification_delivered_count"
    NOTIFICATION_FAILED_COUNT = "notification_failed_count"


@dataclass(frozen=True, slots=True)
class RuntimeMetricsSnapshot:
    """ある時点のランタイム累積メトリクス。"""

    generated_at: datetime
    counts: dict[RuntimeMetricName, int]

    def __post_init__(self) -> None:
        """日時と件数を検証して防御的コピーを作成する。"""

        if self.generated_at.tzinfo is None:
            raise ValueError(
                "集計日時にはタイムゾーンが必要です。"
            )

        normalized = {
            RuntimeMetricName(metric): int(value)
            for metric, value in self.counts.items()
        }

        if any(value < 0 for value in normalized.values()):
            raise ValueError(
                "ランタイムメトリクス件数は0以上である必要があります。"
            )

        for metric in RuntimeMetricName:
            normalized.setdefault(metric, 0)

        object.__setattr__(
            self,
            "counts",
            dict(normalized),
        )

    def get(
        self,
        metric: RuntimeMetricName,
    ) -> int:
        """指定メトリクスの値を返す。"""

        return self.counts[metric]

    @property
    def domain_event_count(self) -> int:
        """Domain Event総数を返す。"""

        return self.get(
            RuntimeMetricName.DOMAIN_EVENT_COUNT
        )

    @property
    def error_count(self) -> int:
        """Error Event総数を返す。"""

        return self.get(
            RuntimeMetricName.ERROR_OCCURRED_COUNT
        )

    @property
    def notification_attempt_count(self) -> int:
        """通知成功・失敗の合計を返す。"""

        return (
            self.get(
                RuntimeMetricName
                .NOTIFICATION_DELIVERED_COUNT
            )
            + self.get(
                RuntimeMetricName
                .NOTIFICATION_FAILED_COUNT
            )
        )

    @property
    def error_rate(self) -> float:
        """Domain Event総数に対するError Event比率を返す。"""

        if self.domain_event_count == 0:
            return 0.0

        return self.error_count / self.domain_event_count

    @property
    def notification_failure_rate(self) -> float:
        """通知試行数に対する失敗率を返す。"""

        attempts = self.notification_attempt_count

        if attempts == 0:
            return 0.0

        return (
            self.get(
                RuntimeMetricName
                .NOTIFICATION_FAILED_COUNT
            )
            / attempts
        )
