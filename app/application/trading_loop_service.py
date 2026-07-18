"""既存Live TradingをRuntime Session・Resource監視へ接続する。"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime, timezone
from typing import Protocol

from app.application.trading_loop_models import (
    TradingLoopCycleResult,
    TradingLoopCycleStatus,
)
from app.live.live_orchestrator_models import LiveCycleResult
from app.runtime.resource_integration import (
    RuntimeResourceIntegrationResult,
)
from app.runtime.resource_models import RuntimeResourceStatus
from app.runtime.session_models import RuntimeSessionSnapshot


class TradingLoopLiveOrchestrator(Protocol):
    """Trading Loopが利用する既存Live Orchestrator。"""

    def run_cycle(
        self,
        *,
        cycle_number: int,
        codes: Iterable[str],
        continue_on_error: bool = True,
    ) -> LiveCycleResult:
        """市場監視とPaper Tradingを1回実行する。"""


class TradingLoopRuntimeSession(Protocol):
    """Trading Loopが利用するRuntime Session。"""

    def record_cycle(
        self,
        *,
        successful: bool,
    ) -> RuntimeSessionSnapshot:
        """サイクル成否を記録する。"""

    def record_heartbeat(self) -> RuntimeSessionSnapshot:
        """Heartbeatを記録する。"""


class TradingLoopResourceIntegration(Protocol):
    """Trading Loopが利用するResource統合処理。"""

    def sample_once(
        self,
        *,
        continue_on_notification_error: bool = True,
    ) -> RuntimeResourceIntegrationResult:
        """Resource監視を1回実行する。"""


class TradingLoopService:
    """既存Live Cycleを運用基盤へ統合する。"""

    def __init__(
        self,
        *,
        live_orchestrator: TradingLoopLiveOrchestrator,
        runtime_session: TradingLoopRuntimeSession,
        resource_integration: (
            TradingLoopResourceIntegration | None
        ) = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        """依存関係と時計を設定する。"""

        self.live_orchestrator = live_orchestrator
        self.runtime_session = runtime_session
        self.resource_integration = resource_integration
        self.now_provider = (
            now_provider
            if now_provider is not None
            else lambda: datetime.now(timezone.utc)
        )

    def run_cycle(
        self,
        *,
        cycle_number: int,
        codes: Iterable[str],
        continue_on_error: bool = True,
        continue_on_notification_error: bool = True,
    ) -> TradingLoopCycleResult:
        """1回のLive Cycleと運用記録を実行する。"""

        if cycle_number <= 0:
            raise ValueError(
                "サイクル番号は0より大きい必要があります。"
            )

        normalized_codes = tuple(
            dict.fromkeys(
                code.strip()
                for code in codes
                if code.strip()
            )
        )

        if not normalized_codes:
            raise ValueError(
                "監視対象銘柄を1件以上指定してください。"
            )

        started_at = self._current_time()
        live_result: LiveCycleResult | None = None
        resource_result: (
            RuntimeResourceIntegrationResult | None
        ) = None

        try:
            live_result = self.live_orchestrator.run_cycle(
                cycle_number=cycle_number,
                codes=normalized_codes,
                continue_on_error=continue_on_error,
            )

            if self.resource_integration is not None:
                resource_result = (
                    self.resource_integration.sample_once(
                        continue_on_notification_error=(
                            continue_on_notification_error
                        ),
                    )
                )

            resource_is_critical = (
                resource_result is not None
                and resource_result.evaluation.status
                is RuntimeResourceStatus.CRITICAL
            )
            successful = (
                live_result.is_completed
                and not resource_is_critical
            )

            self.runtime_session.record_cycle(
                successful=successful
            )
            runtime_snapshot = (
                self.runtime_session.record_heartbeat()
            )

            if live_result.is_failed:
                status = TradingLoopCycleStatus.FAILED
                error_message = (
                    live_result.error_message
                    or "Live Cycleに失敗しました。"
                )
            elif resource_is_critical:
                status = (
                    TradingLoopCycleStatus
                    .RESOURCE_CRITICAL
                )
                error_message = None
            else:
                status = TradingLoopCycleStatus.COMPLETED
                error_message = None

            return TradingLoopCycleResult(
                cycle_number=cycle_number,
                started_at=started_at,
                completed_at=self._current_time(),
                status=status,
                live_cycle_result=live_result,
                runtime_session_snapshot=runtime_snapshot,
                resource_result=resource_result,
                error_message=error_message,
            )

        except Exception as error:
            if not continue_on_error:
                raise

            self.runtime_session.record_cycle(
                successful=False
            )
            runtime_snapshot = (
                self.runtime_session.record_heartbeat()
            )

            return TradingLoopCycleResult(
                cycle_number=cycle_number,
                started_at=started_at,
                completed_at=self._current_time(),
                status=TradingLoopCycleStatus.FAILED,
                live_cycle_result=live_result,
                runtime_session_snapshot=runtime_snapshot,
                resource_result=resource_result,
                error_message=(
                    str(error).strip()
                    or type(error).__name__
                ),
            )

    def _current_time(self) -> datetime:
        """UTCへ正規化した現在日時を返す。"""

        current = self.now_provider()

        if current.tzinfo is None:
            raise ValueError(
                "現在日時にはタイムゾーンが必要です。"
            )

        return current.astimezone(timezone.utc)
