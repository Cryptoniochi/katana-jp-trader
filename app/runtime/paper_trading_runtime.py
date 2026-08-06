"""Trading LoopとPortfolioを終日Paper Tradingとして集約する。"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from app.risk.risk_engine import RiskEngineResult
from app.risk.risk_engine_runner import RiskEngineRunner
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


DEFAULT_RUNTIME_STATUS_PATH = Path(
    "reports/service/paper_trading_runtime_status.json"
)


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
    """1営業日のTrading Cycle・資産推移・リスク状態を集約する。"""

    def __init__(
        self,
        *,
        cycle_runner: PaperTradingCycleRunner,
        portfolio_reader: PaperTradingPortfolioReader,
        risk_runner: RiskEngineRunner | None = None,
        heartbeat_service: RuntimeHeartbeatService | None = None,
        status_path: Path | None = DEFAULT_RUNTIME_STATUS_PATH,
        process_id_provider: Callable[[], int] = os.getpid,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        """Trading Loop・Portfolio・Risk・Heartbeat・時計を設定する。"""

        self.cycle_runner = cycle_runner
        self.portfolio_reader = portfolio_reader
        self.risk_runner = risk_runner
        self.heartbeat_service = heartbeat_service
        self.status_path = (
            None
            if status_path is None
            else Path(status_path)
        )
        self.process_id_provider = process_id_provider
        self.last_status_publish_error: str | None = None
        self.now_provider = (
            now_provider
            if now_provider is not None
            else lambda: datetime.now(timezone.utc)
        )

        self._started_at: datetime | None = None
        self._records: list[PaperTradingCycleRecord] = []
        self._initial_equity: float | None = None
        self._initial_unrealized_profit_loss: float | None = None
        self._external_execution_count = 0
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

    @property
    def last_risk_result(
        self,
    ) -> RiskEngineResult | None:
        """最新のRisk Engine結果を返す。"""

        for record in reversed(self._records):
            if record.risk_result is not None:
                return record.risk_result

        return None

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
        self._initial_unrealized_profit_loss = (
            initial_snapshot.total_unrealized_profit_loss
        )
        self._external_execution_count = 0
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
        self._publish_runtime_status(
            generated_at=started_at,
            portfolio_snapshot=initial_snapshot,
            error_message=None,
        )

    def run_cycle(self) -> PaperTradingCycleRecord:
        """Trading Cycle・Portfolio取得・Risk判定を実行する。"""

        self._require_running()
        cycle_result = self.cycle_runner.run_cycle()
        recorded_at = self._current_time()
        snapshot = self.portfolio_reader.create_snapshot(
            generated_at=recorded_at
        )
        risk_result = self._run_risk_evaluation(
            cycle_result=cycle_result,
            portfolio_snapshot=snapshot,
            evaluated_at=recorded_at,
        )
        record = PaperTradingCycleRecord(
            cycle_result=cycle_result,
            portfolio_snapshot=snapshot,
            risk_result=risk_result,
        )
        self._records.append(record)

        heartbeat_details: dict[str, object] = {
            "record_count": len(self._records),
            "broker_equity": snapshot.broker_equity,
        }

        if risk_result is not None:
            heartbeat_details.update(
                {
                    "risk_evaluated": True,
                    "risk_blocked": risk_result.is_blocked,
                    "allows_new_entries": (
                        risk_result.allows_new_entries
                    ),
                    "approved_quantity": (
                        risk_result.approved_quantity
                    ),
                }
            )
        else:
            heartbeat_details["risk_evaluated"] = False

        self._record_heartbeat(
            event="cycle_completed",
            recorded_at=recorded_at,
            details=heartbeat_details,
        )
        self._publish_runtime_status(
            generated_at=recorded_at,
            portfolio_snapshot=snapshot,
            error_message=None,
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

    def record_external_executions(
        self,
        count: int,
    ) -> None:
        """通常Cycle外で発生した約定数をRuntimeへ加算する。"""

        self._require_running()
        normalized = int(count)

        if normalized < 0:
            raise ValueError(
                "外部約定数は0以上である必要があります。"
            )

        self._external_execution_count += normalized

    def records(
        self,
    ) -> tuple[PaperTradingCycleRecord, ...]:
        """現在までのCycle Recordを返す。"""

        return tuple(self._records)

    def _run_risk_evaluation(
        self,
        *,
        cycle_result: object,
        portfolio_snapshot: PortfolioSnapshot,
        evaluated_at: datetime,
    ) -> RiskEngineResult | None:
        """Risk Runnerが設定されている場合だけリスク判定を行う。"""

        if self.risk_runner is None:
            return None

        run_record = self.risk_runner.run(
            cycle_result=cycle_result,
            portfolio_snapshot=portfolio_snapshot,
            evaluated_at=evaluated_at,
        )

        return run_record.result

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
            external_execution_count=(
                self._external_execution_count
            ),
            error_message=error_message,
        )

        self._status = status
        heartbeat_details: dict[str, object] = {
            "record_count": len(self._records),
            "broker_equity": final_snapshot.broker_equity,
            "risk_evaluated_cycle_count": (
                summary.risk_evaluated_cycle_count
            ),
            "risk_blocked_cycle_count": (
                summary.risk_blocked_cycle_count
            ),
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
        self._publish_runtime_status(
            generated_at=completed_at,
            portfolio_snapshot=final_snapshot,
            error_message=error_message,
        )

        return summary

    def _publish_runtime_status(
        self,
        *,
        generated_at: datetime,
        portfolio_snapshot: PortfolioSnapshot,
        error_message: str | None,
    ) -> None:
        """Dashboard用Runtime状態を原子的に保存する。"""

        if self.status_path is None:
            return

        successful_cycles = sum(
            1
            for record in self._records
            if bool(
                getattr(
                    record.cycle_result,
                    "is_successful",
                    False,
                )
            )
        )
        failed_cycles = (
            len(self._records) - successful_cycles
        )
        signal_count = sum(
            int(
                getattr(
                    record.cycle_result,
                    "signal_count",
                    0,
                )
                or 0
            )
            for record in self._records
        )
        cycle_execution_count = sum(
            int(
                getattr(
                    record.cycle_result,
                    "execution_count",
                    0,
                )
                or 0
            )
            for record in self._records
        )
        execution_count = (
            cycle_execution_count
            + self._external_execution_count
        )
        current_equity = (
            portfolio_snapshot.broker_equity
        )
        session_equity_change = (
            None
            if self._initial_equity is None
            else current_equity - self._initial_equity
        )
        unrealized_profit_loss = sum(
            self._position_unrealized_profit_loss(
                position
            )
            for position in portfolio_snapshot.positions
        )
        initial_unrealized_profit_loss = (
            self._initial_unrealized_profit_loss
            if self._initial_unrealized_profit_loss is not None
            else 0.0
        )
        unrealized_profit_loss_change = (
            unrealized_profit_loss
            - initial_unrealized_profit_loss
        )
        realized_profit_loss = (
            None
            if session_equity_change is None
            else (
                session_equity_change
                - unrealized_profit_loss_change
            )
        )
        total_portfolio_profit_loss = session_equity_change
        pnl_reconciliation_difference = (
            None
            if (
                session_equity_change is None
                or realized_profit_loss is None
            )
            else (
                session_equity_change
                - realized_profit_loss
                - unrealized_profit_loss_change
            )
        )
        pnl_consistent = (
            None
            if pnl_reconciliation_difference is None
            else abs(pnl_reconciliation_difference) < 0.01
        )

        payload = {
            "available": True,
            "generated_at": generated_at.isoformat(),
            "trading_date": (
                None
                if self._started_at is None
                else self._started_at.date().isoformat()
            ),
            "state": (
                "not_started"
                if self._status is None
                else self._status.value
            ),
            "process_id": self.process_id_provider(),
            "started_at": (
                None
                if self._started_at is None
                else self._started_at.isoformat()
            ),
            "last_cycle_at": (
                generated_at.isoformat()
                if self._records
                else None
            ),
            "cycle_count": len(self._records),
            "successful_cycle_count": successful_cycles,
            "failed_cycle_count": failed_cycles,
            "signal_count": signal_count,
            "execution_count": execution_count,
            "cycle_execution_count": cycle_execution_count,
            "external_execution_count": (
                self._external_execution_count
            ),
            "open_position_count": len(
                portfolio_snapshot.positions
            ),
            "portfolio_position_count": len(
                portfolio_snapshot.positions
            ),
            "initial_equity": self._initial_equity,
            "current_equity": current_equity,
            "net_profit_loss": session_equity_change,
            "session_equity_change": session_equity_change,
            "realized_profit_loss": realized_profit_loss,
            "realized_profit_loss_source": (
                "equity_reconciliation"
            ),
            "initial_unrealized_profit_loss": (
                initial_unrealized_profit_loss
            ),
            "unrealized_profit_loss": unrealized_profit_loss,
            "unrealized_profit_loss_change": (
                unrealized_profit_loss_change
            ),
            "total_portfolio_profit_loss": (
                total_portfolio_profit_loss
            ),
            "pnl_reconciliation_difference": (
                pnl_reconciliation_difference
            ),
            "pnl_consistent": pnl_consistent,
            "risk_evaluated_cycle_count": sum(
                1
                for record in self._records
                if record.risk_result is not None
            ),
            "risk_blocked_cycle_count": sum(
                1
                for record in self._records
                if (
                    record.risk_result is not None
                    and record.risk_result.is_blocked
                )
            ),
            "error_message": error_message,
        }

        try:
            self.status_path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )
            temporary = self.status_path.with_suffix(
                self.status_path.suffix + ".tmp"
            )
            temporary.write_text(
                json.dumps(
                    payload,
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            temporary.replace(self.status_path)
            self.last_status_publish_error = None
        except OSError as error:
            self.last_status_publish_error = (
                f"{type(error).__name__}: {error}"
            )

    @staticmethod
    def _position_unrealized_profit_loss(
        position,
    ) -> float:
        """保有ポジションの評価損益を返す。"""

        quantity = float(
            getattr(position, "quantity", 0) or 0
        )
        average_cost = float(
            getattr(position, "average_cost", 0.0)
            or 0.0
        )
        market_price = float(
            getattr(position, "market_price", 0.0)
            or 0.0
        )
        side = getattr(position, "side", None)
        side_text = str(
            getattr(side, "value", side)
        ).lower()

        price_difference = market_price - average_cost

        if side_text in {"short", "sell"}:
            price_difference *= -1.0

        return price_difference * quantity

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
