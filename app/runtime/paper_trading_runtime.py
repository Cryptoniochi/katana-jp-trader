"""Trading LoopとPortfolioを終日Paper Tradingとして集約する。"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Protocol

from app.runtime.paper_trading_runtime_models import (
    PaperTradingCycleRecord,
    PaperTradingDailySummary,
    PaperTradingRuntimeStatus,
)
from app.runtime.runtime_heartbeat_models import (
    RuntimeHeartbeat,
)
from app.runtime.runtime_heartbeat_service import (
    RuntimeHeartbeatService,
)
from app.trading.portfolio_models import PortfolioSnapshot


class PaperTradingCycleRunner(Protocol):
    """終日Runtimeが利用するTrading Loop。"""

    def run_cycle(self):
        """次のTrading Cycleを実行する。"""


class PaperTradingPortfolioReader(Protocol):
    """終日Runtimeが利用するPortfolio取得処理。"""

    def create_snapshot(
        self,
        *,
        generated_at: datetime | None = None,
    ) -> PortfolioSnapshot:
        """現在のPortfolio Snapshotを返す。"""


class PaperTradingRuntime:
    """1営業日のTrading Cycleと資産推移を集約する。"""

    def __init__(
        self,
        *,
        cycle_runner: PaperTradingCycleRunner,
        portfolio_reader: PaperTradingPortfolioReader,
        heartbeat_service: RuntimeHeartbeatService | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        """Trading Loop・Portfolio・Heartbeat・時計を設定する。"""

        self.cycle_runner = cycle_runner
        self.portfolio_reader = portfolio_reader
        self.heartbeat_service = heartbeat_service
        self.now_provider = (
            now_provider
            if now_provider is not None
            else lambda: datetime.now(timezone.utc)
        )

        self._started_at: datetime | None = None
        self._records: list[PaperTradingCycleRecord] = []
        self._initial_equity: float | None = None
        self._status: PaperTradingRuntimeStatus | None = None

    @property
    def status(
        self,
    ) -> PaperTradingRuntimeStatus | None:
        """現在のRuntime状態を返す。"""

        return self._status

    @property
    def last_heartbeat(
        self,
    ) -> RuntimeHeartbeat | None:
        """最新Heartbeatを返す。"""

        if self.heartbeat_service is None:
            return None

        return self.heartbeat_service.last_heartbeat

    def start(self) -> None:
        """終日Runtimeを開始する。"""

        if self._status is PaperTradingRuntimeStatus.RUNNING:
            raise RuntimeError(
                "Paper Trading Runtimeはすでに稼働中です。"
            )

        started_at = self._current_time()
        initial_snapshot = (
            self.portfolio_reader.create_snapshot(
                generated_at=started_at
            )
        )

        self._started_at = started_at
        self._records.clear()
        self._initial_equity = (
            initial_snapshot.broker_equity
        )
        self._status = PaperTradingRuntimeStatus.RUNNING
        self._record_heartbeat(
            event="started",
            recorded_at=started_at,
            details={
                "record_count": 0,
                "broker_equity": (
                    initial_snapshot.broker_equity
                ),
            },
        )

    def run_cycle(self) -> PaperTradingCycleRecord:
        """Trading Cycleを実行してPortfolioを記録する。"""

        self._require_running()
        cycle_result = self.cycle_runner.run_cycle()
        recorded_at = self._current_time()
        snapshot = self.portfolio_reader.create_snapshot(
            generated_at=recorded_at
        )
        record = PaperTradingCycleRecord(
            cycle_result=cycle_result,
            portfolio_snapshot=snapshot,
        )
        self._records.append(record)
        self._record_heartbeat(
            event="cycle_completed",
            recorded_at=recorded_at,
            details={
                "record_count": len(self._records),
                "broker_equity": snapshot.broker_equity,
            },
        )

        return record

    def complete(self) -> PaperTradingDailySummary:
        """正常終了の日次サマリーを返す。"""

        return self._finalize(
            status=PaperTradingRuntimeStatus.COMPLETED,
            error_message=None,
        )

    def fail(
        self,
        *,
        error_message: str,
    ) -> PaperTradingDailySummary:
        """異常終了の日次サマリーを返す。"""

        normalized = error_message.strip()

        if not normalized:
            raise ValueError(
                "異常終了メッセージを指定してください。"
            )

        return self._finalize(
            status=PaperTradingRuntimeStatus.FAILED,
            error_message=normalized,
        )

    def records(
        self,
    ) -> tuple[PaperTradingCycleRecord, ...]:
        """現在までのCycle Recordを返す。"""

        return tuple(self._records)

    def _finalize(
        self,
        *,
        status: PaperTradingRuntimeStatus,
        error_message: str | None,
    ) -> PaperTradingDailySummary:
        """Runtimeを終了して日次集計を返す。"""

        self._require_running()
        completed_at = self._current_time()
        final_snapshot = (
            self.portfolio_reader.create_snapshot(
                generated_at=completed_at
            )
        )

        if self._started_at is None:
            raise RuntimeError(
                "Paper Trading Runtimeが開始されていません。"
            )

        summary = PaperTradingDailySummary(
            trading_date=self._started_at.date(),
            started_at=self._started_at,
            completed_at=completed_at,
            status=status,
            records=tuple(self._records),
            initial_equity=self._initial_equity,
            final_equity=final_snapshot.broker_equity,
            error_message=error_message,
        )

        self._status = status
        heartbeat_details: dict[str, object] = {
            "record_count": len(self._records),
            "broker_equity": final_snapshot.broker_equity,
        }

        if error_message is not None:
            heartbeat_details["error_message"] = error_message

        self._record_heartbeat(
            event=(
                "completed"
                if status is PaperTradingRuntimeStatus.COMPLETED
                else "failed"
            ),
            recorded_at=completed_at,
            details=heartbeat_details,
        )

        return summary

    def _record_heartbeat(
        self,
        *,
        event: str,
        recorded_at: datetime,
        details: dict[str, object],
    ) -> RuntimeHeartbeat | None:
        """Heartbeat Serviceがあれば状態を記録する。"""

        if self.heartbeat_service is None:
            return None

        return self.heartbeat_service.beat(
            recorded_at=recorded_at,
            details={
                "event": event,
                "runtime_status": (
                    None
                    if self._status is None
                    else self._status.value
                ),
                **details,
            },
        )

    def _require_running(self) -> None:
        """稼働中でなければ例外を送出する。"""

        if self._status is not PaperTradingRuntimeStatus.RUNNING:
            raise RuntimeError(
                "Paper Trading Runtimeが稼働していません。"
            )

    def _current_time(self) -> datetime:
        """UTCへ正規化した現在日時を返す。"""

        current = self.now_provider()

        if current.tzinfo is None:
            raise ValueError(
                "現在日時にはタイムゾーンが必要です。"
            )

        return current.astimezone(timezone.utc)
