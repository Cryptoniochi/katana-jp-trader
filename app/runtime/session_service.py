"""長時間運転セッションの開始・集計・日次ローテーションを管理する。"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from uuid import uuid4

from app.runtime.session_models import (
    RuntimeDailySummary,
    RuntimeRotationResult,
    RuntimeSessionReport,
    RuntimeSessionSnapshot,
    RuntimeSessionStatus,
    RuntimeSessionStopReason,
)


class RuntimeSessionService:
    """24時間以上の運転セッションを管理する。"""

    def __init__(
        self,
        *,
        now_provider: Callable[[], datetime] | None = None,
        session_id_provider: Callable[[], str] | None = None,
    ) -> None:
        self.now_provider = (
            now_provider
            if now_provider is not None
            else lambda: datetime.now(timezone.utc)
        )
        self.session_id_provider = (
            session_id_provider
            if session_id_provider is not None
            else lambda: uuid4().hex
        )
        self._session_id: str | None = None
        self._started_at: datetime | None = None
        self._active_date = None
        self._active_day_started_at: datetime | None = None
        self._status: RuntimeSessionStatus | None = None
        self._ended_at: datetime | None = None
        self._stop_reason: RuntimeSessionStopReason | None = None
        self._message: str | None = None
        self._daily_summaries: list[RuntimeDailySummary] = []
        self._reset_active_counters()

    def start(self) -> RuntimeSessionSnapshot:
        """新しいRuntime Sessionを開始する。"""

        if self._status is RuntimeSessionStatus.RUNNING:
            raise RuntimeError(
                "Runtime Sessionはすでに稼働中です。"
            )

        current = self._current_time()
        session_id = self.session_id_provider().strip()

        if not session_id:
            raise ValueError(
                "Runtime Session IDを生成できませんでした。"
            )

        self._session_id = session_id
        self._started_at = current
        self._active_date = current.date()
        self._active_day_started_at = current
        self._status = RuntimeSessionStatus.RUNNING
        self._ended_at = None
        self._stop_reason = None
        self._message = None
        self._daily_summaries.clear()
        self._reset_active_counters()

        return self.snapshot()

    def record_cycle(
        self,
        *,
        successful: bool,
    ) -> RuntimeSessionSnapshot:
        """1サイクルの成否を記録する。"""

        self._require_running()
        self.rotate_if_needed()
        self._cycle_count += 1

        if successful:
            self._successful_cycle_count += 1
        else:
            self._failed_cycle_count += 1
            self._error_count += 1

        return self.snapshot()

    def record_heartbeat(self) -> RuntimeSessionSnapshot:
        """Heartbeatを記録する。"""

        self._require_running()
        self.rotate_if_needed()
        self._heartbeat_count += 1

        return self.snapshot()

    def record_restart(self) -> RuntimeSessionSnapshot:
        """Worker再起動を記録する。"""

        self._require_running()
        self.rotate_if_needed()
        self._restart_count += 1

        return self.snapshot()

    def record_error(self) -> RuntimeSessionSnapshot:
        """サイクル外エラーを記録する。"""

        self._require_running()
        self.rotate_if_needed()
        self._error_count += 1

        return self.snapshot()

    def rotate_if_needed(self) -> RuntimeRotationResult:
        """UTC日付が変わっていれば日次集計を確定する。"""

        self._require_running()
        current = self._current_time()

        if current.date() == self._active_date:
            return RuntimeRotationResult(
                rotated=False,
                previous_summary=None,
                snapshot=self.snapshot(),
            )

        previous = self._finalize_active_day(
            ended_at=current
        )
        self._daily_summaries.append(previous)
        self._active_date = current.date()
        self._active_day_started_at = current
        self._reset_active_counters()

        return RuntimeRotationResult(
            rotated=True,
            previous_summary=previous,
            snapshot=self.snapshot(),
        )

    def stop(
        self,
        *,
        reason: RuntimeSessionStopReason = (
            RuntimeSessionStopReason.NORMAL
        ),
        message: str | None = None,
    ) -> RuntimeSessionReport:
        """セッションを終了して最終レポートを返す。"""

        self._require_running()
        current = self._current_time()
        rotation = self.rotate_if_needed()
        current = self._current_time()

        # 日付変更と停止が同一時刻だった場合、ローテーション直後の
        # 空・0秒サマリーは追加しない。
        if not (
            rotation.rotated
            and self._is_empty_active_day_at(current)
        ):
            self._daily_summaries.append(
                self._finalize_active_day(
                    ended_at=current
                )
            )

        self._ended_at = current
        self._stop_reason = reason
        self._status = (
            RuntimeSessionStatus.FAILED
            if reason is RuntimeSessionStopReason.ERROR
            else RuntimeSessionStatus.STOPPED
        )
        self._message = (
            None
            if message is None
            else message.strip() or None
        )

        return RuntimeSessionReport(
            snapshot=self.snapshot(),
            daily_summaries=tuple(
                self._daily_summaries
            ),
        )

    def snapshot(self) -> RuntimeSessionSnapshot:
        """現在のセッション状態を返す。"""

        if (
            self._session_id is None
            or self._started_at is None
            or self._active_date is None
            or self._status is None
        ):
            raise RuntimeError(
                "Runtime Sessionが開始されていません。"
            )

        return RuntimeSessionSnapshot(
            session_id=self._session_id,
            status=self._status,
            started_at=self._started_at,
            checked_at=self._current_time(),
            active_date=self._active_date,
            cycle_count=self._cycle_count,
            successful_cycle_count=(
                self._successful_cycle_count
            ),
            failed_cycle_count=self._failed_cycle_count,
            heartbeat_count=self._heartbeat_count,
            restart_count=self._restart_count,
            error_count=self._error_count,
            completed_day_count=len(
                self._daily_summaries
            ),
            ended_at=self._ended_at,
            stop_reason=self._stop_reason,
            message=self._message,
        )

    def daily_summaries(
        self,
    ) -> tuple[RuntimeDailySummary, ...]:
        """確定済み日次集計を返す。"""

        return tuple(self._daily_summaries)

    def _finalize_active_day(
        self,
        *,
        ended_at: datetime,
    ) -> RuntimeDailySummary:
        """現在日の集計を確定する。"""

        if (
            self._session_id is None
            or self._active_date is None
            or self._active_day_started_at is None
        ):
            raise RuntimeError(
                "Runtime Sessionが開始されていません。"
            )

        return RuntimeDailySummary(
            session_id=self._session_id,
            operating_date=self._active_date,
            started_at=self._active_day_started_at,
            ended_at=ended_at,
            cycle_count=self._cycle_count,
            successful_cycle_count=(
                self._successful_cycle_count
            ),
            failed_cycle_count=self._failed_cycle_count,
            heartbeat_count=self._heartbeat_count,
            restart_count=self._restart_count,
            error_count=self._error_count,
        )

    def _is_empty_active_day_at(
        self,
        current: datetime,
    ) -> bool:
        """現在日が開始直後の空集計か返す。"""

        return (
            self._active_day_started_at == current
            and self._cycle_count == 0
            and self._heartbeat_count == 0
            and self._restart_count == 0
            and self._error_count == 0
        )

    def _reset_active_counters(self) -> None:
        """現在日の集計値を0へ戻す。"""

        self._cycle_count = 0
        self._successful_cycle_count = 0
        self._failed_cycle_count = 0
        self._heartbeat_count = 0
        self._restart_count = 0
        self._error_count = 0

    def _require_running(self) -> None:
        """稼働中でなければ例外を送出する。"""

        if self._status is not RuntimeSessionStatus.RUNNING:
            raise RuntimeError(
                "Runtime Sessionが稼働していません。"
            )

    def _current_time(self) -> datetime:
        """UTCへ正規化した現在日時を返す。"""

        current = self.now_provider()

        if current.tzinfo is None:
            raise ValueError(
                "現在日時にはタイムゾーンが必要です。"
            )

        return current.astimezone(timezone.utc)
