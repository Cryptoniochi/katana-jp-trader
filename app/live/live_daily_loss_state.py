"""決済取引の正本からLive Kill Switch用損失状態を読み取る。"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from datetime import date, datetime, timezone
from typing import Protocol

from app.runtime.daily_report_service import DailyTradeRecord


NowProvider = Callable[[], datetime]


class DailyClosedTradeRepository(Protocol):
    """対象日の決済済み取引を返すread-only Repository。"""

    def list_closed_trades(
        self,
        report_date: date,
    ) -> tuple[DailyTradeRecord, ...]:
        """対象日に決済された取引を返す。"""


class LiveDailyLossStateProvider:
    """当日の決済済み取引から実現損益と連敗数を取得する。

    `SQLiteDailyTradeRepository` が再構成した決済取引だけを使用する。
    DB取得失敗や不正損益値は握り潰さず例外にし、上位の
    `LiveRuntimeKillSwitchStateProvider` にfail-closedさせる。
    """

    def __init__(
        self,
        *,
        repository: DailyClosedTradeRepository,
        now_provider: NowProvider | None = None,
    ) -> None:
        self.repository = repository
        self.now_provider = (
            now_provider
            if now_provider is not None
            else lambda: datetime.now(timezone.utc)
        )

    def daily_realized_profit_loss(self) -> float:
        """当日決済取引の実現損益合計を返す。"""

        records = self._records()
        return float(
            sum(
                self._validated_profit_loss(record)
                for record in records
            )
        )

    def consecutive_loss_count(self) -> int:
        """当日末尾から連続している損失取引数を返す。

        損益0または利益取引で連敗は終了する。
        """

        records = self._records()
        count = 0

        for record in reversed(records):
            value = self._validated_profit_loss(record)
            if value < 0:
                count += 1
                continue
            break

        return count

    def _records(self) -> tuple[DailyTradeRecord, ...]:
        # Runtimeの標準時刻はUTCで、日次取引Repositoryは日本営業日を
        # 受け取るためAsia/Tokyoへ明示変換する。
        from zoneinfo import ZoneInfo

        report_date = self._now().astimezone(
            ZoneInfo("Asia/Tokyo")
        ).date()

        records = self.repository.list_closed_trades(report_date)
        return self._validate_order(records)

    @staticmethod
    def _validate_order(
        records: Sequence[DailyTradeRecord],
    ) -> tuple[DailyTradeRecord, ...]:
        resolved = tuple(records)
        previous: datetime | None = None

        for record in resolved:
            closed_at = record.closed_at
            if closed_at.tzinfo is None:
                raise ValueError(
                    "決済日時にはタイムゾーンが必要です。"
                )
            normalized = closed_at.astimezone(timezone.utc)
            if previous is not None and normalized < previous:
                raise ValueError(
                    "決済取引はclosed_at昇順である必要があります。"
                )
            previous = normalized
            LiveDailyLossStateProvider._validated_profit_loss(
                record
            )

        return resolved

    @staticmethod
    def _validated_profit_loss(
        record: DailyTradeRecord,
    ) -> float:
        value = float(record.realized_profit_loss)
        if not math.isfinite(value):
            raise ValueError(
                "実現損益には有限値が必要です。"
            )
        return value

    def _now(self) -> datetime:
        current = self.now_provider()
        if current.tzinfo is None:
            raise ValueError(
                "現在日時にはタイムゾーンが必要です。"
            )
        return current.astimezone(timezone.utc)
