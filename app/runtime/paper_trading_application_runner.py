"""終日Paper Tradingの開始・実行・停止・保存を統括する。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.application.trading_loop_runner_models import (
    TradingLoopRunnerResult,
    TradingLoopRunnerStopReason,
)
from app.runtime.paper_trading_runtime_models import (
    PaperTradingDailySummary,
)


class PaperTradingLifecycleComponent(Protocol):
    """終日実行で開始・停止するTrading Loop Component。"""

    def start(self) -> None:
        """Componentを開始する。"""

    def stop(self) -> None:
        """Componentを停止する。"""


class PaperTradingDailyRuntime(Protocol):
    """終日集計を開始するPaper Trading Runtime。"""

    def start(self) -> None:
        """日次Runtimeを開始する。"""


class PaperTradingMarketRunner(Protocol):
    """市場時間に従ってTrading Cycleを実行するRunner。"""

    def run(self) -> TradingLoopRunnerResult:
        """Trading Loopを実行する。"""


class PaperTradingRuntimePersistence(Protocol):
    """Runtime終了と日次保存を行うService。"""

    def complete_and_persist(self):
        """正常終了して日次サマリーを保存する。"""

    def fail_and_persist(
        self,
        *,
        error_message: str,
    ):
        """異常終了して日次サマリーを保存する。"""


@dataclass(frozen=True, slots=True)
class PaperTradingApplicationResult:
    """終日Paper Trading Applicationの実行結果。"""

    runner_result: TradingLoopRunnerResult
    daily_summary: PaperTradingDailySummary

    @property
    def is_successful(self) -> bool:
        """正常終了として保存されたか返す。"""

        return self.daily_summary.error_message is None


class PaperTradingApplicationRunner:
    """終日Paper Tradingのライフサイクルを統括する。"""

    FAILURE_STOP_REASONS = frozenset(
        {
            TradingLoopRunnerStopReason.ERROR,
            TradingLoopRunnerStopReason.CYCLE_FAILED,
            TradingLoopRunnerStopReason.RESOURCE_CRITICAL,
        }
    )

    def __init__(
        self,
        *,
        component: PaperTradingLifecycleComponent,
        runtime: PaperTradingDailyRuntime,
        market_runner: PaperTradingMarketRunner,
        persistence_service: PaperTradingRuntimePersistence,
    ) -> None:
        """実行に必要な依存関係を設定する。"""

        self.component = component
        self.runtime = runtime
        self.market_runner = market_runner
        self.persistence_service = persistence_service

    def run(self) -> PaperTradingApplicationResult:
        """開始から日次結果保存までを一括実行する。"""

        component_started = False
        runtime_started = False
        runner_result: TradingLoopRunnerResult | None = None

        try:
            self.component.start()
            component_started = True

            self.runtime.start()
            runtime_started = True

            runner_result = self.market_runner.run()

            stop_error = self._stop_component(
                component_started=component_started
            )
            component_started = False

            failure_message = self._resolve_failure_message(
                runner_result=runner_result,
                stop_error=stop_error,
            )

            if failure_message is not None:
                persistence_result = (
                    self.persistence_service.fail_and_persist(
                        error_message=failure_message
                    )
                )
            else:
                persistence_result = (
                    self.persistence_service.complete_and_persist()
                )

            return PaperTradingApplicationResult(
                runner_result=runner_result,
                daily_summary=persistence_result.summary,
            )

        except Exception as error:
            primary_message = (
                str(error).strip()
                or type(error).__name__
            )

            stop_error = self._stop_component(
                component_started=component_started
            )
            component_started = False

            combined_message = self._combine_error_messages(
                primary_message,
                stop_error,
            )

            if runtime_started:
                self.persistence_service.fail_and_persist(
                    error_message=combined_message
                )

            raise

        finally:
            if component_started:
                self._stop_component(
                    component_started=True
                )

    def _stop_component(
        self,
        *,
        component_started: bool,
    ) -> str | None:
        """開始済みComponentを停止してエラー文字列を返す。"""

        if not component_started:
            return None

        try:
            self.component.stop()
        except Exception as error:
            return (
                str(error).strip()
                or type(error).__name__
            )

        return None

    def _resolve_failure_message(
        self,
        *,
        runner_result: TradingLoopRunnerResult,
        stop_error: str | None,
    ) -> str | None:
        """Runner終了理由と停止失敗から異常終了理由を返す。"""

        messages: list[str] = []

        if runner_result.stop_reason in self.FAILURE_STOP_REASONS:
            messages.append(
                runner_result.error_message
                or (
                    "Trading Loopが異常終了しました。 "
                    f"reason={runner_result.stop_reason.value}"
                )
            )

        if stop_error is not None:
            messages.append(
                "Trading Loop Componentの停止に失敗しました。 "
                f"error={stop_error}"
            )

        if not messages:
            return None

        return " / ".join(messages)

    @staticmethod
    def _combine_error_messages(
        primary_message: str,
        stop_error: str | None,
    ) -> str:
        """実行例外と停止例外を一つの文字列へまとめる。"""

        if stop_error is None:
            return primary_message

        return (
            f"{primary_message} / "
            "Trading Loop Componentの停止に失敗しました。 "
            f"error={stop_error}"
        )