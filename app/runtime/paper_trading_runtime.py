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
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        """Trading Loop・Portfolio・時計を設定する。"""

        self.cycle_runner = cycle_runner
        self.portfolio_reader = portfolio_reader
        self.now_provider = (
            now_provider
            if now_provider is not None
            else lambda: datetime.now(timezone.utc)
        )

        self._started_at: datetime | None = None
        self._records: list[PaperTradingCycleRecord] = []
        self._initial_equity: float | None = None
        self._status: PaperTradingRuntimeStatus | None = None

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

    def run_cycle(self) -> PaperTradingCycleRecord:
        """Trading Cycleを実行してPortfolioを記録する。"""

        self._require_running()
        cycle_result = self.cycle_runner.run_cycle()
        snapshot = self.portfolio_reader.create_snapshot(
            generated_at=self._current_time()
        )
        record = PaperTradingCycleRecord(
            cycle_result=cycle_result,
            portfolio_snapshot=snapshot,
        )
        self._records.append(record)

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


    @property
    def status(
        self,
    ) -> PaperTradingRuntimeStatus | None:
        """現在のRuntime状態を返す。"""

        return self._status

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

        return summary

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
