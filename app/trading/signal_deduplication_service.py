"""営業日単位で売買シグナルの重複を判定・抑止する。"""

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Protocol
from zoneinfo import ZoneInfo

from app.trading.signal_models import (
    SignalAction,
    SignalStatus,
    TradeSignal,
    TradeSignalRecord,
)
from app.trading.signal_repository import (
    DuplicateSignalError,
)


JAPAN_TIMEZONE = ZoneInfo(
    "Asia/Tokyo",
)


class SignalDeduplicationDecision(StrEnum):
    """重複判定結果。"""

    ACCEPTED = "accepted"
    DUPLICATE = "duplicate"
    FAILED = "failed"


class TradeSignalRepositoryReaderWriter(Protocol):
    """重複判定で使用するSignalRepositoryのインターフェース。"""

    def list_recent(
        self,
        *,
        limit: int = 100,
        code: str | None = None,
        strategy_name: str | None = None,
        status: SignalStatus | None = None,
        action: SignalAction | None = None,
    ) -> list[TradeSignalRecord]:
        """条件に一致するシグナルを新しい順に返す。"""

    def save(
        self,
        signal: TradeSignal,
    ) -> TradeSignalRecord:
        """シグナルを保存する。"""


@dataclass(frozen=True, slots=True)
class SignalDeduplicationResult:
    """1件のシグナルに対する重複判定・保存結果。"""

    decision: SignalDeduplicationDecision
    signal: TradeSignal
    trading_date: date

    saved_record: TradeSignalRecord | None
    duplicate_record: TradeSignalRecord | None
    message: str | None

    @property
    def is_accepted(self) -> bool:
        """新規採用されたか返す。"""

        return (
            self.decision
            is SignalDeduplicationDecision.ACCEPTED
        )

    @property
    def is_duplicate(self) -> bool:
        """重複として拒否されたか返す。"""

        return (
            self.decision
            is SignalDeduplicationDecision.DUPLICATE
        )

    @property
    def is_failed(self) -> bool:
        """判定または保存に失敗したか返す。"""

        return (
            self.decision
            is SignalDeduplicationDecision.FAILED
        )


@dataclass(frozen=True, slots=True)
class SignalDeduplicationBatchResult:
    """複数シグナルの重複判定結果。"""

    results: tuple[
        SignalDeduplicationResult,
        ...,
    ]

    @property
    def input_count(self) -> int:
        """入力シグナル数を返す。"""

        return len(
            self.results,
        )

    @property
    def accepted_count(self) -> int:
        """採用件数を返す。"""

        return sum(
            result.is_accepted
            for result in self.results
        )

    @property
    def duplicate_count(self) -> int:
        """重複件数を返す。"""

        return sum(
            result.is_duplicate
            for result in self.results
        )

    @property
    def failed_count(self) -> int:
        """失敗件数を返す。"""

        return sum(
            result.is_failed
            for result in self.results
        )

    @property
    def saved_records(
        self,
    ) -> tuple[
        TradeSignalRecord,
        ...,
    ]:
        """新規保存されたレコードを返す。"""

        return tuple(
            result.saved_record
            for result in self.results
            if result.saved_record is not None
        )

    @property
    def is_successful(self) -> bool:
        """保存失敗がないか返す。"""

        return self.failed_count == 0


class SignalDeduplicationService:
    """同一営業日の同種シグナルを保存前に抑止する。"""

    BLOCKING_STATUSES = frozenset(
        {
            SignalStatus.PENDING,
            SignalStatus.PROCESSED,
        }
    )

    def __init__(
        self,
        repository: TradeSignalRepositoryReaderWriter,
        *,
        search_limit: int = 1000,
    ) -> None:
        """SignalRepositoryと検索上限を設定する。"""

        if search_limit <= 0:
            raise ValueError(
                "重複検索件数は0より大きい必要があります。"
            )

        self.repository = repository
        self.search_limit = search_limit

    def save_if_unique(
        self,
        signal: TradeSignal,
        *,
        continue_on_error: bool = True,
    ) -> SignalDeduplicationResult:
        """営業日内で重複していなければシグナルを保存する。"""

        trading_date = self.resolve_trading_date(
            signal,
        )

        try:
            duplicate_record = self.find_duplicate(
                signal,
            )

            if duplicate_record is not None:
                return SignalDeduplicationResult(
                    decision=(
                        SignalDeduplicationDecision.DUPLICATE
                    ),
                    signal=signal,
                    trading_date=trading_date,
                    saved_record=None,
                    duplicate_record=duplicate_record,
                    message=(
                        "同一営業日に有効な同種シグナルが"
                        "既に存在します。 "
                        f"existing_signal_id="
                        f"{duplicate_record.signal_id}"
                    ),
                )

            saved_record = self.repository.save(
                signal,
            )

        except DuplicateSignalError:
            concurrent_duplicate = self.find_duplicate(
                signal,
            )

            return SignalDeduplicationResult(
                decision=(
                    SignalDeduplicationDecision.DUPLICATE
                ),
                signal=signal,
                trading_date=trading_date,
                saved_record=None,
                duplicate_record=concurrent_duplicate,
                message=(
                    "同一シグナルが同時実行により"
                    "先に保存されました。"
                ),
            )

        except Exception as error:
            if not continue_on_error:
                raise

            return SignalDeduplicationResult(
                decision=(
                    SignalDeduplicationDecision.FAILED
                ),
                signal=signal,
                trading_date=trading_date,
                saved_record=None,
                duplicate_record=None,
                message=str(
                    error,
                ),
            )

        return SignalDeduplicationResult(
            decision=(
                SignalDeduplicationDecision.ACCEPTED
            ),
            signal=signal,
            trading_date=trading_date,
            saved_record=saved_record,
            duplicate_record=None,
            message=None,
        )

    def save_many(
        self,
        signals: list[TradeSignal],
        *,
        continue_on_error: bool = True,
    ) -> SignalDeduplicationBatchResult:
        """複数シグナルを順番に重複判定して保存する。"""

        results: list[
            SignalDeduplicationResult
        ] = []

        for signal in sorted(
            signals,
            key=lambda item: (
                item.generated_at,
                item.code,
                item.strategy_name,
                item.action.value,
                item.signal_id,
            ),
        ):
            result = self.save_if_unique(
                signal,
                continue_on_error=continue_on_error,
            )

            results.append(
                result,
            )

        return SignalDeduplicationBatchResult(
            results=tuple(
                results,
            ),
        )

    def find_duplicate(
        self,
        signal: TradeSignal,
    ) -> TradeSignalRecord | None:
        """同一営業日の有効な同種シグナルを返す。"""

        trading_date = self.resolve_trading_date(
            signal,
        )

        records = self.repository.list_recent(
            limit=self.search_limit,
            code=signal.code,
            strategy_name=signal.strategy_name,
            action=signal.action,
        )

        for record in records:
            if (
                record.status
                not in self.BLOCKING_STATUSES
            ):
                continue

            existing_trading_date = (
                self.resolve_trading_date(
                    record.signal,
                )
            )

            if (
                existing_trading_date
                == trading_date
            ):
                return record

        return None

    @staticmethod
    def resolve_trading_date(
        signal: TradeSignal,
    ) -> date:
        """シグナル生成日時を日本時間の営業日へ変換する。"""

        if signal.generated_at.tzinfo is None:
            raise ValueError(
                "シグナル生成日時には"
                "タイムゾーンが必要です。"
            )

        return (
            signal.generated_at
            .astimezone(
                JAPAN_TIMEZONE,
            )
            .date()
        )