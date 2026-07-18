"""PaperTradingRuntimeの終了と日次保存を一体化する。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.runtime.paper_trading_persistence_service import (
    PaperTradingPersistenceResult,
)
from app.runtime.paper_trading_runtime_models import (
    PaperTradingDailySummary,
)


class PaperTradingRuntimeFinalizer(Protocol):
    """終了可能なPaper Trading Runtime。"""

    def complete(self) -> PaperTradingDailySummary:
        """正常終了する。"""

    def fail(
        self,
        *,
        error_message: str,
    ) -> PaperTradingDailySummary:
        """異常終了する。"""


class PaperTradingSummaryPersister(Protocol):
    """日次サマリー永続化処理。"""

    def persist(
        self,
        summary: PaperTradingDailySummary,
    ) -> PaperTradingPersistenceResult:
        """日次サマリーを保存する。"""


@dataclass(frozen=True, slots=True)
class PaperTradingRuntimePersistenceResult:
    """Runtime終了と永続化をまとめた結果。"""

    persistence: PaperTradingPersistenceResult

    @property
    def summary(self) -> PaperTradingDailySummary:
        """日次サマリーを返す。"""

        return self.persistence.summary


class PaperTradingRuntimePersistenceService:
    """Runtime終了後に日次結果を必ず保存する。"""

    def __init__(
        self,
        *,
        runtime: PaperTradingRuntimeFinalizer,
        persistence_service: PaperTradingSummaryPersister,
    ) -> None:
        """RuntimeとPersistence Serviceを設定する。"""

        self.runtime = runtime
        self.persistence_service = persistence_service

    def complete_and_persist(
        self,
    ) -> PaperTradingRuntimePersistenceResult:
        """正常終了して日次サマリーを保存する。"""

        summary = self.runtime.complete()
        persistence = self.persistence_service.persist(
            summary
        )

        return PaperTradingRuntimePersistenceResult(
            persistence=persistence
        )

    def fail_and_persist(
        self,
        *,
        error_message: str,
    ) -> PaperTradingRuntimePersistenceResult:
        """異常終了して日次サマリーを保存する。"""

        summary = self.runtime.fail(
            error_message=error_message
        )
        persistence = self.persistence_service.persist(
            summary
        )

        return PaperTradingRuntimePersistenceResult(
            persistence=persistence
        )
