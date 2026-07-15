"""市場時間足の差分更新範囲を安全に判定する。"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum
from typing import Protocol


class LatestMarketBarReader(Protocol):
    """保存済み時間足の最新日時を取得するインターフェース。"""

    def latest_datetime(
        self,
        code: str,
        interval_minutes: int,
    ) -> datetime | None:
        """指定銘柄・時間足の最新保存日時を返す。"""


class TradingCalendarReader(Protocol):
    """指定期間の営業日を取得するインターフェース。"""

    def get_business_dates(
        self,
        start_date: date,
        end_date: date,
    ) -> list[date]:
        """指定期間内の営業日一覧を返す。"""


class IncrementalUpdateAction(StrEnum):
    """銘柄ごとの差分更新判定を表す。"""

    UPDATE = "update"
    SKIP_UP_TO_DATE = "skip_up_to_date"
    SKIP_NO_BUSINESS_DATES = "skip_no_business_dates"


@dataclass(frozen=True, slots=True)
class IncrementalUpdateTask:
    """1銘柄の差分更新計画を表す。"""

    code: str
    interval_minutes: int
    latest_saved_at: datetime | None
    requested_start_date: date
    requested_end_date: date
    business_dates: tuple[date, ...]
    action: IncrementalUpdateAction

    @property
    def should_update(self) -> bool:
        """API取得が必要な計画か返す。"""

        return self.action is IncrementalUpdateAction.UPDATE

    @property
    def update_start_date(self) -> date | None:
        """実際の更新対象となる最初の営業日を返す。"""

        if not self.business_dates:
            return None

        return self.business_dates[0]

    @property
    def update_end_date(self) -> date | None:
        """実際の更新対象となる最後の営業日を返す。"""

        if not self.business_dates:
            return None

        return self.business_dates[-1]

    @property
    def business_date_count(self) -> int:
        """更新対象営業日数を返す。"""

        return len(self.business_dates)


@dataclass(frozen=True, slots=True)
class IncrementalUpdatePlan:
    """複数銘柄の差分更新計画を表す。"""

    initial_start_date: date
    target_end_date: date
    interval_minutes: int
    tasks: tuple[IncrementalUpdateTask, ...]

    @property
    def code_count(self) -> int:
        """計画に含まれる銘柄数を返す。"""

        return len(self.tasks)

    @property
    def update_tasks(self) -> tuple[IncrementalUpdateTask, ...]:
        """更新が必要な銘柄だけを返す。"""

        return tuple(
            task
            for task in self.tasks
            if task.should_update
        )

    @property
    def skipped_tasks(self) -> tuple[IncrementalUpdateTask, ...]:
        """更新不要としてスキップする銘柄だけを返す。"""

        return tuple(
            task
            for task in self.tasks
            if not task.should_update
        )

    @property
    def update_code_count(self) -> int:
        """更新が必要な銘柄数を返す。"""

        return len(self.update_tasks)

    @property
    def skipped_code_count(self) -> int:
        """スキップする銘柄数を返す。"""

        return len(self.skipped_tasks)

    @property
    def total_business_date_count(self) -> int:
        """全銘柄の更新対象営業日数合計を返す。"""

        return sum(
            task.business_date_count
            for task in self.tasks
        )

    @property
    def is_up_to_date(self) -> bool:
        """すべての銘柄が更新不要か返す。"""

        return not self.update_tasks


class IncrementalUpdatePlanner:
    """保存済みデータから銘柄別の差分更新範囲を決定する。"""

    def __init__(
        self,
        repository: LatestMarketBarReader,
        calendar_reader: TradingCalendarReader,
    ) -> None:
        """最新日時Repositoryと取引カレンダーを設定する。"""

        self.repository = repository
        self.calendar_reader = calendar_reader

    def create_plan(
        self,
        codes: Sequence[str],
        *,
        initial_start_date: date,
        target_end_date: date,
        interval_minutes: int = 5,
        today: date | None = None,
    ) -> IncrementalUpdatePlan:
        """複数銘柄の差分更新計画を作成する。

        保存済みデータがない銘柄は ``initial_start_date`` から更新する。
        保存済みデータがある銘柄は、最新保存日の翌日から更新する。

        ``target_end_date`` より新しい保存データがある場合や、
        最新保存日が ``target_end_date`` と同日の場合は更新不要とする。

        取引カレンダー上の営業日が1日も存在しない場合も、
        APIを呼び出さないスキップ計画とする。
        """

        normalized_codes = self._normalize_codes(codes)

        self._validate_arguments(
            initial_start_date=initial_start_date,
            target_end_date=target_end_date,
            interval_minutes=interval_minutes,
            today=today,
        )

        latest_by_code = {
            code: self.repository.latest_datetime(
                code=code,
                interval_minutes=interval_minutes,
            )
            for code in normalized_codes
        }

        requested_start_by_code = {
            code: self._resolve_requested_start_date(
                latest_saved_at=latest_by_code[code],
                initial_start_date=initial_start_date,
            )
            for code in normalized_codes
        }

        calendar_start_date = min(
            requested_start_by_code.values()
        )

        all_business_dates: tuple[date, ...] = ()

        if calendar_start_date <= target_end_date:
            all_business_dates = self._normalize_business_dates(
                self.calendar_reader.get_business_dates(
                    start_date=calendar_start_date,
                    end_date=target_end_date,
                ),
                start_date=calendar_start_date,
                end_date=target_end_date,
            )

        tasks = tuple(
            self._create_task(
                code=code,
                interval_minutes=interval_minutes,
                latest_saved_at=latest_by_code[code],
                requested_start_date=(
                    requested_start_by_code[code]
                ),
                requested_end_date=target_end_date,
                all_business_dates=all_business_dates,
            )
            for code in normalized_codes
        )

        return IncrementalUpdatePlan(
            initial_start_date=initial_start_date,
            target_end_date=target_end_date,
            interval_minutes=interval_minutes,
            tasks=tasks,
        )

    @staticmethod
    def _resolve_requested_start_date(
        *,
        latest_saved_at: datetime | None,
        initial_start_date: date,
    ) -> date:
        """保存状況から更新要求開始日を決定する。"""

        if latest_saved_at is None:
            return initial_start_date

        return latest_saved_at.date() + timedelta(days=1)

    @staticmethod
    def _create_task(
        *,
        code: str,
        interval_minutes: int,
        latest_saved_at: datetime | None,
        requested_start_date: date,
        requested_end_date: date,
        all_business_dates: tuple[date, ...],
    ) -> IncrementalUpdateTask:
        """1銘柄の差分更新計画を作成する。"""

        if requested_start_date > requested_end_date:
            return IncrementalUpdateTask(
                code=code,
                interval_minutes=interval_minutes,
                latest_saved_at=latest_saved_at,
                requested_start_date=requested_start_date,
                requested_end_date=requested_end_date,
                business_dates=(),
                action=(
                    IncrementalUpdateAction.SKIP_UP_TO_DATE
                ),
            )

        business_dates = tuple(
            business_date
            for business_date in all_business_dates
            if (
                requested_start_date
                <= business_date
                <= requested_end_date
            )
        )

        if not business_dates:
            return IncrementalUpdateTask(
                code=code,
                interval_minutes=interval_minutes,
                latest_saved_at=latest_saved_at,
                requested_start_date=requested_start_date,
                requested_end_date=requested_end_date,
                business_dates=(),
                action=(
                    IncrementalUpdateAction.SKIP_NO_BUSINESS_DATES
                ),
            )

        return IncrementalUpdateTask(
            code=code,
            interval_minutes=interval_minutes,
            latest_saved_at=latest_saved_at,
            requested_start_date=requested_start_date,
            requested_end_date=requested_end_date,
            business_dates=business_dates,
            action=IncrementalUpdateAction.UPDATE,
        )

    @staticmethod
    def _normalize_business_dates(
        business_dates: Sequence[date],
        *,
        start_date: date,
        end_date: date,
    ) -> tuple[date, ...]:
        """営業日を期間内に限定し、重複除去して昇順にする。"""

        return tuple(
            sorted(
                {
                    business_date
                    for business_date in business_dates
                    if start_date <= business_date <= end_date
                }
            )
        )

    @staticmethod
    def _normalize_codes(
        codes: Sequence[str],
    ) -> tuple[str, ...]:
        """銘柄コードを検証し、順序を維持して重複除去する。"""

        if not codes:
            raise ValueError(
                "銘柄コードを1件以上指定してください。"
            )

        normalized_codes: list[str] = []

        for code in codes:
            normalized_code = code.strip()

            if not normalized_code.isdigit():
                raise ValueError(
                    "銘柄コードは数字で指定してください。"
                )

            if len(normalized_code) not in (4, 5):
                raise ValueError(
                    "銘柄コードは4桁または5桁で指定してください。"
                )

            if normalized_code not in normalized_codes:
                normalized_codes.append(normalized_code)

        return tuple(normalized_codes)

    @staticmethod
    def _validate_arguments(
        *,
        initial_start_date: date,
        target_end_date: date,
        interval_minutes: int,
        today: date | None,
    ) -> None:
        """差分更新条件を検証する。"""

        if initial_start_date > target_end_date:
            raise ValueError(
                "初回取得開始日は更新終了日以前にしてください。"
            )

        if interval_minutes <= 0:
            raise ValueError(
                "時間足の間隔は0より大きい必要があります。"
            )

        resolved_today = today or date.today()

        if target_end_date > resolved_today:
            raise ValueError(
                "更新終了日に未来日は指定できません。"
            )