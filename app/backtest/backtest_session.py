"""バックテストの1回の実行単位を管理する。"""

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import Callable

from app.backtest.strategy_runner import (
    BacktestStrategyRunner,
    StrategyRunResult,
)
from app.trading.signal_models import TradeSignal


class BacktestSessionStatus(StrEnum):
    """バックテストセッションの終了状態。"""

    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class BacktestSessionResult:
    """1回のバックテストセッション結果。"""

    session_id: str
    strategy_name: str
    status: BacktestSessionStatus
    started_at: datetime
    finished_at: datetime
    strategy_result: StrategyRunResult | None
    error_message: str | None

    def __post_init__(self) -> None:
        """セッション結果の整合性を検証する。"""

        normalized_session_id = self.session_id.strip()
        normalized_strategy_name = self.strategy_name.strip()

        if not normalized_session_id:
            raise ValueError(
                "セッションIDを指定してください。"
            )

        if not normalized_strategy_name:
            raise ValueError(
                "戦略名を指定してください。"
            )

        if self.started_at.tzinfo is None:
            raise ValueError(
                "開始日時にはタイムゾーンが必要です。"
            )

        if self.finished_at.tzinfo is None:
            raise ValueError(
                "終了日時にはタイムゾーンが必要です。"
            )

        if self.finished_at < self.started_at:
            raise ValueError(
                "終了日時は開始日時以後である必要があります。"
            )

        if (
            self.status is BacktestSessionStatus.COMPLETED
            and self.strategy_result is None
        ):
            raise ValueError(
                "完了セッションには戦略実行結果が必要です。"
            )

        if (
            self.status is BacktestSessionStatus.FAILED
            and not (self.error_message or "").strip()
        ):
            raise ValueError(
                "失敗セッションにはエラーメッセージが必要です。"
            )

        object.__setattr__(
            self,
            "session_id",
            normalized_session_id,
        )
        object.__setattr__(
            self,
            "strategy_name",
            normalized_strategy_name,
        )

    @property
    def is_completed(self) -> bool:
        """正常完了したか返す。"""

        return self.status is BacktestSessionStatus.COMPLETED

    @property
    def is_failed(self) -> bool:
        """失敗したか返す。"""

        return self.status is BacktestSessionStatus.FAILED

    @property
    def frame_count(self) -> int:
        """処理したFrame件数を返す。"""

        if self.strategy_result is None:
            return 0

        return self.strategy_result.frame_count

    @property
    def signal_count(self) -> int:
        """生成シグナル件数を返す。"""

        if self.strategy_result is None:
            return 0

        return self.strategy_result.signal_count

    @property
    def signals(self) -> tuple[TradeSignal, ...]:
        """生成された全シグナルを返す。"""

        if self.strategy_result is None:
            return ()

        return self.strategy_result.signals

    @property
    def duration_seconds(self) -> float:
        """セッション実行時間を秒で返す。"""

        return (
            self.finished_at - self.started_at
        ).total_seconds()


class BacktestSession:
    """StrategyRunnerを1回のセッションとして実行する。"""

    def __init__(
        self,
        *,
        session_id: str,
        strategy_runner: BacktestStrategyRunner,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        """セッションID、Runner、時計を設定する。"""

        normalized_session_id = session_id.strip()

        if not normalized_session_id:
            raise ValueError(
                "セッションIDを指定してください。"
            )

        self.session_id = normalized_session_id
        self.strategy_runner = strategy_runner
        self.now_provider = (
            now_provider
            if now_provider is not None
            else lambda: datetime.now(timezone.utc)
        )

    def run(
        self,
        *,
        continue_on_error: bool = False,
    ) -> BacktestSessionResult:
        """戦略Runnerを実行してセッション結果を返す。"""

        started_at = self._current_time()

        try:
            strategy_result = self.strategy_runner.run()
            finished_at = self._current_time()

            return BacktestSessionResult(
                session_id=self.session_id,
                strategy_name=(
                    self.strategy_runner.strategy_name
                ),
                status=BacktestSessionStatus.COMPLETED,
                started_at=started_at,
                finished_at=finished_at,
                strategy_result=strategy_result,
                error_message=None,
            )

        except Exception as error:
            if not continue_on_error:
                raise

            finished_at = self._current_time()

            return BacktestSessionResult(
                session_id=self.session_id,
                strategy_name=(
                    self.strategy_runner.strategy_name
                ),
                status=BacktestSessionStatus.FAILED,
                started_at=started_at,
                finished_at=finished_at,
                strategy_result=None,
                error_message=str(error),
            )

    def _current_time(self) -> datetime:
        """現在日時をUTCへ正規化する。"""

        current = self.now_provider()

        if current.tzinfo is None:
            raise ValueError(
                "現在日時にはタイムゾーンが必要です。"
            )

        return current.astimezone(timezone.utc)
