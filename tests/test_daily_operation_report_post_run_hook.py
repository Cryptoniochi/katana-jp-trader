"""DailyOperationReportPostRunHookのテスト。"""

from app.runtime.daily_operation_report_post_run_hook import (
    DailyOperationReportPostRunHook,
)


class FakePublisher:
    def __init__(self) -> None:
        self.results = []

    def publish(self, result):
        self.results.append(result)
        return object()


def test_hook_delegates_to_report_publisher() -> None:
    publisher = FakePublisher()
    hook = DailyOperationReportPostRunHook(
        report_publisher=publisher
    )
    result = object()

    hook.handle(result)

    assert publisher.results == [result]
