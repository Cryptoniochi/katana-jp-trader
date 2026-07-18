"""Paper Trading Runtime終了結果を永続化する。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.runtime.paper_trading_daily_repository import (
    PaperTradingDailyRecord,
)
from app.runtime.paper_trading_runtime_models import (
    PaperTradingDailySummary,
)


class PaperTradingDailyWriter(Protocol):
    """日次サマリー保存処理。"""

    def save(
        self,
        summary: PaperTradingDailySummary,
    ) -> PaperTradingDailyRecord:
        """日次サマリーを保存する。"""


@dataclass(frozen=True, slots=True)
class PaperTradingPersistenceResult:
    """Paper Trading日次保存結果。"""

    summary: PaperTradingDailySummary
    record: PaperTradingDailyRecord

    @property
    def trading_date(self):
        """営業日を返す。"""

        return self.record.trading_date


class PaperTradingPersistenceService:
    """Paper Trading日次結果をRepositoryへ保存する。"""

    def __init__(
        self,
        *,
        daily_repository: PaperTradingDailyWriter,
    ) -> None:
        """日次Repositoryを設定する。"""

        self.daily_repository = daily_repository

    def persist(
        self,
        summary: PaperTradingDailySummary,
    ) -> PaperTradingPersistenceResult:
        """日次サマリーを永続化する。"""

        record = self.daily_repository.save(summary)

        return PaperTradingPersistenceResult(
            summary=summary,
            record=record,
        )
