"""Paper Trading運用後の後処理を一元管理する。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.runtime.daily_operation_report_publish_service import (
    DailyOperationReportPublishResult,
)
from app.runtime.paper_trading_day_models import (
    PaperTradingDayResult,
)


class TradingOperationRunner(Protocol):
    """1営業日のPaper Trading運用処理。"""

    def run(self) -> PaperTradingDayResult:
        """1営業日の運用結果を返す。"""


class TradingOperationReportPublisher(Protocol):
    """日次運用レポート公開処理。"""

    def publish(
        self,
        result: PaperTradingDayResult,
    ) -> DailyOperationReportPublishResult:
        """日次JSON・HTMLレポートを生成する。"""


class TradingOperationHook(Protocol):
    """将来の通知・監視向け任意Hook。"""

    def handle(
        self,
        result: PaperTradingDayResult,
    ) -> None:
        """運用結果を受け取って後処理する。"""


@dataclass(frozen=True, slots=True)
class TradingOperationOrchestratorSettings:
    """運用後処理の継続可否設定。"""

    continue_on_report_error: bool = True
    continue_on_hook_error: bool = True


@dataclass(frozen=True, slots=True)
class TradingOperationResult:
    """Paper Trading運用と後処理をまとめた結果。"""

    operation_result: PaperTradingDayResult
    report_result: DailyOperationReportPublishResult | None
    report_error_message: str | None
    completed_hook_count: int
    hook_error_messages: tuple[str, ...]

    def __post_init__(self) -> None:
        """結果の整合性を検証する。"""

        report_error_message = (
            None
            if self.report_error_message is None
            else self.report_error_message.strip() or None
        )

        if self.completed_hook_count < 0:
            raise ValueError(
                "完了Hook数は0以上である必要があります。"
            )

        if (
            self.report_result is not None
            and report_error_message is not None
        ):
            raise ValueError(
                "レポート成功時にエラーは設定できません。"
            )

        object.__setattr__(
            self,
            "report_error_message",
            report_error_message,
        )

    @property
    def trading_date(self):
        """営業日を返す。"""

        return self.operation_result.trading_date

    @property
    def report_published(self) -> bool:
        """日次レポートが生成されたか返す。"""

        return self.report_result is not None

    @property
    def hook_failure_count(self) -> int:
        """失敗Hook数を返す。"""

        return len(self.hook_error_messages)


class TradingOperationOrchestrator:
    """運用・日次レポート・任意Hookを順番に実行する。"""

    def __init__(
        self,
        *,
        operation_runner: TradingOperationRunner,
        report_publisher: TradingOperationReportPublisher | None = None,
        hooks: tuple[TradingOperationHook, ...] = (),
        settings: TradingOperationOrchestratorSettings | None = None,
    ) -> None:
        """Runner・Report Publisher・Hookを設定する。"""

        self.operation_runner = operation_runner
        self.report_publisher = report_publisher
        self.hooks = tuple(hooks)
        self.settings = (
            settings
            if settings is not None
            else TradingOperationOrchestratorSettings()
        )

    def run(self) -> TradingOperationResult:
        """1営業日の運用と後処理を実行する。"""

        operation_result = self.operation_runner.run()

        report_result: (
            DailyOperationReportPublishResult | None
        ) = None
        report_error_message: str | None = None

        if self.report_publisher is not None:
            try:
                report_result = self.report_publisher.publish(
                    operation_result
                )
            except Exception as error:
                if not self.settings.continue_on_report_error:
                    raise

                report_error_message = (
                    str(error).strip()
                    or type(error).__name__
                )

        completed_hook_count = 0
        hook_error_messages: list[str] = []

        for hook in self.hooks:
            try:
                hook.handle(operation_result)
                completed_hook_count += 1
            except Exception as error:
                if not self.settings.continue_on_hook_error:
                    raise

                hook_error_messages.append(
                    str(error).strip()
                    or type(error).__name__
                )

        return TradingOperationResult(
            operation_result=operation_result,
            report_result=report_result,
            report_error_message=report_error_message,
            completed_hook_count=completed_hook_count,
            hook_error_messages=tuple(
                hook_error_messages
            ),
        )
