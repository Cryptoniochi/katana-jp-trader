"""Trading LoopをApplication Componentとして提供する。"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from app.application.trading_loop_models import (
    TradingLoopCycleResult,
)
from app.application.trading_loop_service import (
    TradingLoopService,
)
from app.runtime.session_models import (
    RuntimeSessionReport,
    RuntimeSessionStopReason,
)


class TradingLoopRuntimeLifecycle(Protocol):
    """Trading Loop Componentが利用するSession Lifecycle。"""

    def start(self):
        """Runtime Sessionを開始する。"""

    def stop(
        self,
        *,
        reason: RuntimeSessionStopReason,
        message: str | None = None,
    ) -> RuntimeSessionReport:
        """Runtime Sessionを終了する。"""


class TradingLoopComponent:
    """Application Orchestratorへ登録できるTrading Loop。"""

    def __init__(
        self,
        *,
        service: TradingLoopService,
        runtime_session: TradingLoopRuntimeLifecycle,
        codes: Iterable[str],
        continue_on_error: bool = True,
        continue_on_notification_error: bool = True,
    ) -> None:
        """Service・Session・監視対象銘柄を設定する。"""

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

        self.service = service
        self.runtime_session = runtime_session
        self.codes = normalized_codes
        self.continue_on_error = continue_on_error
        self.continue_on_notification_error = (
            continue_on_notification_error
        )
        self._running = False
        self._next_cycle_number = 1
        self._last_session_report: (
            RuntimeSessionReport | None
        ) = None

    @property
    def component_name(self) -> str:
        """Application Component名を返す。"""

        return "trading-loop"

    @property
    def is_running(self) -> bool:
        """Componentが稼働中か返す。"""

        return self._running

    @property
    def last_session_report(
        self,
    ) -> RuntimeSessionReport | None:
        """直近のSession終了レポートを返す。"""

        return self._last_session_report

    def start(self) -> None:
        """Runtime Sessionを開始する。"""

        if self._running:
            raise RuntimeError(
                "Trading Loopはすでに稼働中です。"
            )

        self.runtime_session.start()
        self._running = True
        self._next_cycle_number = 1
        self._last_session_report = None

    def run_cycle(self) -> TradingLoopCycleResult:
        """次のTrading Cycleを1回実行する。"""

        if not self._running:
            raise RuntimeError(
                "Trading Loopが開始されていません。"
            )

        result = self.service.run_cycle(
            cycle_number=self._next_cycle_number,
            codes=self.codes,
            continue_on_error=self.continue_on_error,
            continue_on_notification_error=(
                self.continue_on_notification_error
            ),
        )
        self._next_cycle_number += 1

        return result

    def stop(self) -> None:
        """Runtime Sessionを正常終了する。"""

        if not self._running:
            raise RuntimeError(
                "Trading Loopが開始されていません。"
            )

        self._last_session_report = (
            self.runtime_session.stop(
                reason=RuntimeSessionStopReason.NORMAL,
                message="Trading Loop stopped.",
            )
        )
        self._running = False
