"""Trading CycleとRiskEngineを接続するアダプター。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from app.risk.risk_engine import (
    RiskEngineRequest,
    RiskEngineResult,
)
from app.trading.portfolio_models import PortfolioSnapshot


class RiskEngineEvaluator(Protocol):
    """Risk Engine評価処理のインターフェース。"""

    def evaluate(
        self,
        request: RiskEngineRequest,
    ) -> RiskEngineResult:
        """統合リスク判定を実行する。"""


class RiskEngineRequestFactory(Protocol):
    """Cycle情報からRisk Engine入力を生成する。"""

    def create_request(
        self,
        *,
        cycle_result: object,
        portfolio_snapshot: PortfolioSnapshot,
        evaluated_at: datetime,
    ) -> RiskEngineRequest:
        """Risk Engineへ渡す入力を返す。"""


@dataclass(frozen=True, slots=True)
class RiskEngineRunRecord:
    """1回分のRisk Engine実行記録。"""

    cycle_result: object
    portfolio_snapshot: PortfolioSnapshot
    request: RiskEngineRequest
    result: RiskEngineResult
    evaluated_at: datetime

    def __post_init__(self) -> None:
        """評価時刻をUTCへ正規化する。"""

        if self.evaluated_at.tzinfo is None:
            raise ValueError(
                "評価時刻にはタイムゾーンが必要です。"
            )

        object.__setattr__(
            self,
            "evaluated_at",
            self.evaluated_at.astimezone(timezone.utc),
        )

    @property
    def allows_new_entries(self) -> bool:
        """新規エントリーを許可するか返す。"""

        return self.result.allows_new_entries

    @property
    def is_blocked(self) -> bool:
        """リスク判定が停止状態か返す。"""

        return self.result.is_blocked

    @property
    def approved_quantity(self) -> int:
        """承認された注文数量を返す。"""

        return self.result.approved_quantity


class RiskEngineRunner:
    """Trading Cycle後のRisk Engine実行を集約する。"""

    def __init__(
        self,
        *,
        risk_engine: RiskEngineEvaluator,
        request_factory: RiskEngineRequestFactory,
    ) -> None:
        """Risk EngineとRequest Factoryを設定する。"""

        self.risk_engine = risk_engine
        self.request_factory = request_factory
        self._last_record: RiskEngineRunRecord | None = None
        self._run_count = 0

    @property
    def last_record(self) -> RiskEngineRunRecord | None:
        """最新の実行記録を返す。"""

        return self._last_record

    @property
    def run_count(self) -> int:
        """Risk Engine実行回数を返す。"""

        return self._run_count

    def run(
        self,
        *,
        cycle_result: object,
        portfolio_snapshot: PortfolioSnapshot,
        evaluated_at: datetime,
    ) -> RiskEngineRunRecord:
        """Request生成・Risk評価・実行記録作成を行う。"""

        normalized_at = self._normalize_datetime(
            evaluated_at
        )
        request = self.request_factory.create_request(
            cycle_result=cycle_result,
            portfolio_snapshot=portfolio_snapshot,
            evaluated_at=normalized_at,
        )
        result = self.risk_engine.evaluate(request)
        record = RiskEngineRunRecord(
            cycle_result=cycle_result,
            portfolio_snapshot=portfolio_snapshot,
            request=request,
            result=result,
            evaluated_at=normalized_at,
        )

        self._last_record = record
        self._run_count += 1

        return record

    def allows_new_entries(
        self,
        *,
        cycle_result: object,
        portfolio_snapshot: PortfolioSnapshot,
        evaluated_at: datetime,
    ) -> bool:
        """Risk Engineを実行して新規エントリー可否を返す。"""

        return self.run(
            cycle_result=cycle_result,
            portfolio_snapshot=portfolio_snapshot,
            evaluated_at=evaluated_at,
        ).allows_new_entries

    @staticmethod
    def _normalize_datetime(
        value: datetime,
    ) -> datetime:
        """タイムゾーン付き日時をUTCへ正規化する。"""

        if value.tzinfo is None:
            raise ValueError(
                "評価時刻にはタイムゾーンが必要です。"
            )

        return value.astimezone(timezone.utc)
