"""Heartbeat・稼働時間・再起動判定を管理する。"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from app.supervisor.supervisor_models import (
    RestartDecision,
    SupervisorPolicy,
    SupervisorSnapshot,
    SupervisorStatus,
    SupervisorStopReason,
)


class SupervisorService:
    """1つの長時間稼働Workerを監視する。"""

    def __init__(
        self,
        *,
        worker_name: str,
        policy: SupervisorPolicy | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        """Worker名・方針・時計を設定する。"""

        worker_name = worker_name.strip()

        if not worker_name:
            raise ValueError(
                "Worker名を指定してください。"
            )

        self.worker_name = worker_name
        self.policy = policy or SupervisorPolicy()
        self.now_provider = (
            now_provider
            if now_provider is not None
            else lambda: datetime.now(timezone.utc)
        )

        self._started_at: datetime | None = None
        self._last_heartbeat_at: datetime | None = None
        self._last_restart_at: datetime | None = None
        self._restart_count = 0
        self._status = SupervisorStatus.STOPPED
        self._stop_reason = SupervisorStopReason.MANUAL
        self._message: str | None = None

    def start(self) -> SupervisorSnapshot:
        """Worker監視を開始する。"""

        current = self._current_time()
        self._started_at = current
        self._last_heartbeat_at = current
        self._status = SupervisorStatus.RUNNING
        self._stop_reason = None
        self._message = None

        return self.snapshot()

    def record_heartbeat(
        self,
        *,
        occurred_at: datetime | None = None,
    ) -> SupervisorSnapshot:
        """WorkerのHeartbeatを記録する。"""

        if self._started_at is None:
            raise RuntimeError(
                "Supervisor開始前にHeartbeatを記録できません。"
            )

        resolved = (
            self._normalize_time(occurred_at)
            if occurred_at is not None
            else self._current_time()
        )

        if resolved < self._started_at:
            raise ValueError(
                "Heartbeat日時は開始日時以後である必要があります。"
            )

        if (
            self._last_heartbeat_at is not None
            and resolved < self._last_heartbeat_at
        ):
            raise ValueError(
                "Heartbeat日時は前回以後である必要があります。"
            )

        self._last_heartbeat_at = resolved
        self._status = SupervisorStatus.RUNNING
        self._stop_reason = None
        self._message = None

        return self.snapshot()

    def check(self) -> SupervisorSnapshot:
        """Heartbeat Timeoutを評価して現在状態を返す。"""

        snapshot = self.snapshot()

        if (
            snapshot.status is SupervisorStatus.RUNNING
            and snapshot.heartbeat_age_seconds is not None
            and snapshot.heartbeat_age_seconds
            > self.policy.heartbeat_timeout_seconds
        ):
            self._status = SupervisorStatus.STALE
            self._stop_reason = (
                SupervisorStopReason.HEARTBEAT_TIMEOUT
            )
            self._message = (
                "Heartbeatがタイムアウトしました。 "
                f"age_seconds="
                f"{snapshot.heartbeat_age_seconds:.3f}"
            )
            snapshot = self.snapshot()

        return snapshot

    def stop(
        self,
        *,
        reason: SupervisorStopReason = (
            SupervisorStopReason.MANUAL
        ),
        message: str | None = None,
    ) -> SupervisorSnapshot:
        """Worker監視を停止する。"""

        if self._started_at is None:
            raise RuntimeError(
                "Supervisor開始前に停止できません。"
            )

        self._status = (
            SupervisorStatus.STOPPED
            if reason
            in {
                SupervisorStopReason.NORMAL,
                SupervisorStopReason.MANUAL,
            }
            else SupervisorStatus.FAILED
        )
        self._stop_reason = reason
        self._message = (
            None
            if message is None
            else message.strip() or None
        )

        return self.snapshot()

    def restart_decision(self) -> RestartDecision:
        """現在状態から再起動可否を返す。"""

        snapshot = self.check()

        if snapshot.status not in {
            SupervisorStatus.STALE,
            SupervisorStatus.FAILED,
        }:
            return RestartDecision(
                should_restart=False,
                reason=None,
                next_restart_at=None,
                message="Workerは再起動対象ではありません。",
            )

        if self._restart_count >= self.policy.maximum_restart_count:
            self._status = SupervisorStatus.FAILED
            self._stop_reason = (
                SupervisorStopReason.RESTART_LIMIT
            )
            self._message = (
                "最大再起動回数に到達しました。"
            )
            return RestartDecision(
                should_restart=False,
                reason=SupervisorStopReason.RESTART_LIMIT,
                next_restart_at=None,
                message=self._message,
            )

        current = self._current_time()

        if self._last_restart_at is not None:
            cooldown_base = self._last_restart_at
        elif self._started_at is not None:
            cooldown_base = self._started_at
        else:
            cooldown_base = current

        next_restart_at = (
            cooldown_base
            + timedelta(
                seconds=self.policy.restart_cooldown_seconds
            )
        )

        if next_restart_at < current:
            next_restart_at = current

        return RestartDecision(
            should_restart=True,
            reason=(
                snapshot.stop_reason
                or SupervisorStopReason.ERROR
            ),
            next_restart_at=next_restart_at,
            message="Workerを再起動できます。",
        )

    def mark_restarted(self) -> SupervisorSnapshot:
        """再起動実施を記録し、新しい稼働期間を開始する。"""

        decision = self.restart_decision()

        if not decision.should_restart:
            raise RuntimeError(
                "現在の状態ではWorkerを再起動できません。"
            )

        current = self._current_time()

        if (
            decision.next_restart_at is not None
            and current < decision.next_restart_at
        ):
            raise RuntimeError(
                "再起動Cooldown中です。"
            )

        self._restart_count += 1
        self._last_restart_at = current
        self._started_at = current
        self._last_heartbeat_at = current
        self._status = SupervisorStatus.RUNNING
        self._stop_reason = None
        self._message = None

        return self.snapshot()

    def snapshot(self) -> SupervisorSnapshot:
        """現在状態をSnapshotとして返す。"""

        if self._started_at is None:
            raise RuntimeError(
                "Supervisorが開始されていません。"
            )

        return SupervisorSnapshot(
            worker_name=self.worker_name,
            status=self._status,
            started_at=self._started_at,
            checked_at=self._current_time(),
            last_heartbeat_at=self._last_heartbeat_at,
            last_restart_at=self._last_restart_at,
            restart_count=self._restart_count,
            stop_reason=self._stop_reason,
            message=self._message,
        )

    def reset_restart_count(self) -> None:
        """再起動回数を0へ戻す。"""

        self._restart_count = 0

    def _current_time(self) -> datetime:
        """UTCへ正規化した現在日時を返す。"""

        return self._normalize_time(
            self.now_provider()
        )

    @staticmethod
    def _normalize_time(
        value: datetime,
    ) -> datetime:
        """タイムゾーン付き日時をUTCへ正規化する。"""

        if value.tzinfo is None:
            raise ValueError(
                "日時にはタイムゾーンが必要です。"
            )

        return value.astimezone(timezone.utc)
