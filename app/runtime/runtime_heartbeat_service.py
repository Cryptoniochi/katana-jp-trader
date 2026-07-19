"""Trading RuntimeのHeartbeatを記録・監視する。"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any

from app.runtime.runtime_heartbeat_models import (
    RuntimeHeartbeat,
    RuntimeHeartbeatSnapshot,
)


class RuntimeHeartbeatService:
    """Runtime Heartbeatの記録と生存判定を管理する。"""

    def __init__(
        self,
        *,
        source: str = "paper_trading_runtime",
        stale_after: timedelta = timedelta(minutes=2),
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        """発生元、失効閾値、時計を設定する。"""

        normalized_source = source.strip()

        if not normalized_source:
            raise ValueError(
                "Heartbeat sourceを指定してください。"
            )

        if stale_after <= timedelta(0):
            raise ValueError(
                "Heartbeat stale_afterは0より大きい必要があります。"
            )

        self.source = normalized_source
        self.stale_after = stale_after
        self.now_provider = (
            now_provider
            if now_provider is not None
            else lambda: datetime.now(timezone.utc)
        )

        self._last_heartbeat: RuntimeHeartbeat | None = None
        self._next_sequence = 1
        self._lock = Lock()

    @property
    def last_heartbeat(
        self,
    ) -> RuntimeHeartbeat | None:
        """最新Heartbeatを返す。"""

        with self._lock:
            return self._last_heartbeat

    @property
    def next_sequence(
        self,
    ) -> int:
        """次に採番されるsequenceを返す。"""

        with self._lock:
            return self._next_sequence

    def beat(
        self,
        *,
        details: dict[str, Any] | None = None,
        recorded_at: datetime | None = None,
    ) -> RuntimeHeartbeat:
        """Heartbeatを1件記録して返す。"""

        heartbeat_time = (
            self._normalize_datetime(recorded_at)
            if recorded_at is not None
            else self._current_time()
        )
        normalized_details = (
            {}
            if details is None
            else dict(details)
        )

        with self._lock:
            heartbeat = RuntimeHeartbeat(
                sequence=self._next_sequence,
                recorded_at=heartbeat_time,
                source=self.source,
                details=normalized_details,
            )
            self._last_heartbeat = heartbeat
            self._next_sequence += 1

        return heartbeat

    def snapshot(
        self,
        *,
        checked_at: datetime | None = None,
    ) -> RuntimeHeartbeatSnapshot:
        """現在時点のHeartbeat生存判定を返す。"""

        snapshot_time = (
            self._normalize_datetime(checked_at)
            if checked_at is not None
            else self._current_time()
        )

        with self._lock:
            last_heartbeat = self._last_heartbeat

        return RuntimeHeartbeatSnapshot.create(
            checked_at=snapshot_time,
            last_heartbeat=last_heartbeat,
            stale_after=self.stale_after,
        )

    def reset(self) -> None:
        """Heartbeat履歴とsequenceを初期状態へ戻す。"""

        with self._lock:
            self._last_heartbeat = None
            self._next_sequence = 1

    def restore(
        self,
        *,
        last_heartbeat: RuntimeHeartbeat | None,
    ) -> None:
        """永続化済みの最新Heartbeatから状態を復元する。"""

        with self._lock:
            self._last_heartbeat = last_heartbeat
            self._next_sequence = (
                1
                if last_heartbeat is None
                else last_heartbeat.sequence + 1
            )

    def is_alive(
        self,
        *,
        checked_at: datetime | None = None,
    ) -> bool:
        """現在Heartbeat上で生存しているか返す。"""

        return self.snapshot(
            checked_at=checked_at
        ).is_alive

    def _current_time(self) -> datetime:
        """現在日時をUTCへ正規化して返す。"""

        return self._normalize_datetime(
            self.now_provider()
        )

    @staticmethod
    def _normalize_datetime(
        value: datetime,
    ) -> datetime:
        """タイムゾーン付き日時をUTCへ正規化する。"""

        if value.tzinfo is None:
            raise ValueError(
                "Heartbeat日時にはタイムゾーンが必要です。"
            )

        return value.astimezone(timezone.utc)
