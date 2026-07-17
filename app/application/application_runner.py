"""Applicationの起動・停止・Graceful Shutdownを管理する。"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

from app.application.application_models import (
    ApplicationReport,
    ApplicationSnapshot,
    ApplicationState,
    ApplicationStopReason,
)


class ApplicationRunner:
    """Project KATANAのApplication Lifecycleを管理する。"""

    def __init__(
        self,
        *,
        application_name: str = "Project KATANA",
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        """Application名と時計を設定する。"""

        application_name = application_name.strip()

        if not application_name:
            raise ValueError(
                "Application名を指定してください。"
            )

        self.application_name = application_name
        self.now_provider = (
            now_provider
            if now_provider is not None
            else lambda: datetime.now(timezone.utc)
        )

        self._created_at = self._current_time()
        self._state = ApplicationState.CREATED
        self._started_at: datetime | None = None
        self._stopping_at: datetime | None = None
        self._stopped_at: datetime | None = None
        self._stop_reason: ApplicationStopReason | None = None
        self._message: str | None = None

    def start(self) -> ApplicationSnapshot:
        """Applicationを起動する。"""

        if self._state is not ApplicationState.CREATED:
            raise RuntimeError(
                "CREATED状態からのみ起動できます。 "
                f"state={self._state.value}"
            )

        current = self._current_time()
        self._state = ApplicationState.STARTING
        self._started_at = current
        self._message = None

        self._state = ApplicationState.RUNNING

        return self.snapshot()

    def begin_shutdown(
        self,
        *,
        reason: ApplicationStopReason = (
            ApplicationStopReason.MANUAL
        ),
        message: str | None = None,
    ) -> ApplicationSnapshot:
        """Graceful Shutdownを開始する。"""

        if self._state is not ApplicationState.RUNNING:
            raise RuntimeError(
                "RUNNING状態からのみ停止を開始できます。 "
                f"state={self._state.value}"
            )

        self._state = ApplicationState.STOPPING
        self._stopping_at = self._current_time()
        self._stop_reason = reason
        self._message = (
            None
            if message is None
            else message.strip() or None
        )

        return self.snapshot()

    def complete_shutdown(self) -> ApplicationReport:
        """Graceful Shutdownを完了する。"""

        if self._state is not ApplicationState.STOPPING:
            raise RuntimeError(
                "STOPPING状態からのみ停止を完了できます。 "
                f"state={self._state.value}"
            )

        self._stopped_at = self._current_time()
        self._state = (
            ApplicationState.FAILED
            if self._stop_reason is ApplicationStopReason.ERROR
            else ApplicationState.STOPPED
        )

        snapshot = self.snapshot()

        return ApplicationReport(
            snapshot=snapshot,
            graceful_shutdown=(
                snapshot.state is ApplicationState.STOPPED
            ),
        )

    def stop(
        self,
        *,
        reason: ApplicationStopReason = (
            ApplicationStopReason.MANUAL
        ),
        message: str | None = None,
    ) -> ApplicationReport:
        """停止開始と停止完了を連続して実行する。"""

        self.begin_shutdown(
            reason=reason,
            message=message,
        )
        return self.complete_shutdown()

    def fail(
        self,
        *,
        message: str,
    ) -> ApplicationReport:
        """異常終了を記録する。"""

        message = message.strip()

        if not message:
            raise ValueError(
                "異常終了メッセージを指定してください。"
            )

        return self.stop(
            reason=ApplicationStopReason.ERROR,
            message=message,
        )

    def snapshot(self) -> ApplicationSnapshot:
        """現在状態をSnapshotとして返す。"""

        return ApplicationSnapshot(
            application_name=self.application_name,
            state=self._state,
            created_at=self._created_at,
            checked_at=self._current_time(),
            started_at=self._started_at,
            stopping_at=self._stopping_at,
            stopped_at=self._stopped_at,
            stop_reason=self._stop_reason,
            message=self._message,
        )

    def _current_time(self) -> datetime:
        """UTCへ正規化した現在日時を返す。"""

        current = self.now_provider()

        if current.tzinfo is None:
            raise ValueError(
                "現在日時にはタイムゾーンが必要です。"
            )

        return current.astimezone(timezone.utc)
