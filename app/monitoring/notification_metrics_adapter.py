"""通知配信結果をランタイムメトリクスへ反映する。"""

from __future__ import annotations

from app.monitoring.runtime_metrics import (
    RuntimeMetricName,
)
from app.monitoring.runtime_metrics_service import (
    RuntimeMetricsService,
)
from app.notifications.notification_models import (
    NotificationDeliveryResult,
)


class NotificationMetricsAdapter:
    """通知配信結果から成功・失敗チャネル数を集計する。"""

    def __init__(
        self,
        *,
        service: RuntimeMetricsService,
    ) -> None:
        self.service = service

    def record(
        self,
        result: NotificationDeliveryResult,
    ) -> None:
        """通知配信結果をランタイムメトリクスへ反映する。"""

        if result.delivered_count > 0:
            self.service.increment(
                RuntimeMetricName
                .NOTIFICATION_DELIVERED_COUNT,
                amount=result.delivered_count,
            )

        if result.failed_count > 0:
            self.service.increment(
                RuntimeMetricName
                .NOTIFICATION_FAILED_COUNT,
                amount=result.failed_count,
            )
