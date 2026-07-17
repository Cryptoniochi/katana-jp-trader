"""Domain Eventをランタイムメトリクスへ反映する。"""

from __future__ import annotations

from app.events.domain_events import (
    DomainEvent,
    DomainEventType,
)
from app.monitoring.runtime_metrics import (
    RuntimeMetricName,
)
from app.monitoring.runtime_metrics_service import (
    RuntimeMetricsService,
)


class RuntimeMetricsSubscriber:
    """Domain Event Bus向けのメトリクス購読ハンドラー。"""

    EVENT_METRICS = {
        DomainEventType.SIGNAL_CREATED: (
            RuntimeMetricName.SIGNAL_COUNT
        ),
        DomainEventType.RISK_ASSESSED: (
            RuntimeMetricName.RISK_ASSESSMENT_COUNT
        ),
        DomainEventType.ORDER_CREATED: (
            RuntimeMetricName.ORDER_CREATED_COUNT
        ),
        DomainEventType.ORDER_UPDATED: (
            RuntimeMetricName.ORDER_UPDATED_COUNT
        ),
        DomainEventType.EXECUTION_RECORDED: (
            RuntimeMetricName.EXECUTION_RECORDED_COUNT
        ),
        DomainEventType.PORTFOLIO_UPDATED: (
            RuntimeMetricName.PORTFOLIO_UPDATED_COUNT
        ),
        DomainEventType.RECOVERY_COMPLETED: (
            RuntimeMetricName.RECOVERY_COMPLETED_COUNT
        ),
        DomainEventType.ERROR_OCCURRED: (
            RuntimeMetricName.ERROR_OCCURRED_COUNT
        ),
    }

    def __init__(
        self,
        *,
        service: RuntimeMetricsService,
    ) -> None:
        self.service = service

    def __call__(
        self,
        event: DomainEvent,
    ) -> None:
        """総イベント数と種別別メトリクスを更新する。"""

        self.service.increment(
            RuntimeMetricName.DOMAIN_EVENT_COUNT
        )

        metric = self.EVENT_METRICS.get(
            event.event_type
        )

        if metric is not None:
            self.service.increment(metric)
