"""RiskEngineRunnerのテスト。"""

from datetime import datetime, timedelta, timezone

import pytest

from app.risk.risk_engine_runner import (
    RiskEngineRunner,
)
from app.trading.portfolio_models import PortfolioSnapshot


EVALUATED_AT = datetime(
    2026,
    7,
    19,
    9,
    0,
    tzinfo=timezone.utc,
)


class FakeRiskRequest:
    """テスト用Risk Engine入力。"""

    def __init__(
        self,
        *,
        cycle_result,
        portfolio_snapshot,
        evaluated_at,
    ) -> None:
        self.cycle_result = cycle_result
        self.portfolio_snapshot = portfolio_snapshot
        self.evaluated_at = evaluated_at


class FakeRiskResult:
    """テスト用Risk Engine結果。"""

    def __init__(
        self,
        *,
        allows_new_entries: bool,
        approved_quantity: int,
    ) -> None:
        self.allows_new_entries = allows_new_entries
        self.is_blocked = not allows_new_entries
        self.approved_quantity = (
            approved_quantity
            if allows_new_entries
            else 0
        )


class FakeRequestFactory:
    """呼び出し内容を記録するRequest Factory。"""

    def __init__(self) -> None:
        self.calls = []

    def create_request(
        self,
        *,
        cycle_result,
        portfolio_snapshot,
        evaluated_at,
    ):
        self.calls.append(
            {
                "cycle_result": cycle_result,
                "portfolio_snapshot": portfolio_snapshot,
                "evaluated_at": evaluated_at,
            }
        )

        return FakeRiskRequest(
            cycle_result=cycle_result,
            portfolio_snapshot=portfolio_snapshot,
            evaluated_at=evaluated_at,
        )


class FakeRiskEngine:
    """呼び出し内容を記録するRisk Engine。"""

    def __init__(self, results) -> None:
        self.results = list(results)
        self.requests = []

    def evaluate(self, request):
        self.requests.append(request)

        return self.results[len(self.requests) - 1]


def create_snapshot(
    *,
    generated_at: datetime = EVALUATED_AT,
) -> PortfolioSnapshot:
    """テスト用Portfolio Snapshotを生成する。"""

    return PortfolioSnapshot(
        currency="JPY",
        cash_balance=1_000_000.0,
        buying_power=1_000_000.0,
        broker_market_value=0.0,
        broker_equity=1_000_000.0,
        positions=(),
        generated_at=generated_at,
    )


def test_runner_connects_factory_and_engine() -> None:
    """Factoryで生成した入力をRisk Engineへ渡す。"""

    cycle_result = object()
    snapshot = create_snapshot()
    expected_result = FakeRiskResult(
        allows_new_entries=True,
        approved_quantity=200,
    )
    factory = FakeRequestFactory()
    engine = FakeRiskEngine((expected_result,))
    runner = RiskEngineRunner(
        risk_engine=engine,
        request_factory=factory,
    )

    record = runner.run(
        cycle_result=cycle_result,
        portfolio_snapshot=snapshot,
        evaluated_at=EVALUATED_AT,
    )

    assert len(factory.calls) == 1
    assert len(engine.requests) == 1
    assert engine.requests[0] is record.request
    assert record.result is expected_result
    assert record.cycle_result is cycle_result
    assert record.portfolio_snapshot is snapshot
    assert record.evaluated_at == EVALUATED_AT


def test_runner_exposes_approved_result() -> None:
    """承認結果の補助プロパティを返す。"""

    runner = RiskEngineRunner(
        risk_engine=FakeRiskEngine(
            (
                FakeRiskResult(
                    allows_new_entries=True,
                    approved_quantity=300,
                ),
            )
        ),
        request_factory=FakeRequestFactory(),
    )

    record = runner.run(
        cycle_result=object(),
        portfolio_snapshot=create_snapshot(),
        evaluated_at=EVALUATED_AT,
    )

    assert record.allows_new_entries
    assert not record.is_blocked
    assert record.approved_quantity == 300


def test_runner_exposes_blocked_result() -> None:
    """停止結果では承認数量を0として返す。"""

    runner = RiskEngineRunner(
        risk_engine=FakeRiskEngine(
            (
                FakeRiskResult(
                    allows_new_entries=False,
                    approved_quantity=300,
                ),
            )
        ),
        request_factory=FakeRequestFactory(),
    )

    record = runner.run(
        cycle_result=object(),
        portfolio_snapshot=create_snapshot(),
        evaluated_at=EVALUATED_AT,
    )

    assert not record.allows_new_entries
    assert record.is_blocked
    assert record.approved_quantity == 0


def test_runner_tracks_last_record_and_count() -> None:
    """最新記録と実行回数を保持する。"""

    first_result = FakeRiskResult(
        allows_new_entries=True,
        approved_quantity=100,
    )
    second_result = FakeRiskResult(
        allows_new_entries=False,
        approved_quantity=100,
    )
    runner = RiskEngineRunner(
        risk_engine=FakeRiskEngine(
            (
                first_result,
                second_result,
            )
        ),
        request_factory=FakeRequestFactory(),
    )

    assert runner.last_record is None
    assert runner.run_count == 0

    first_record = runner.run(
        cycle_result=object(),
        portfolio_snapshot=create_snapshot(),
        evaluated_at=EVALUATED_AT,
    )
    second_record = runner.run(
        cycle_result=object(),
        portfolio_snapshot=create_snapshot(),
        evaluated_at=EVALUATED_AT,
    )

    assert runner.run_count == 2
    assert runner.last_record is second_record
    assert runner.last_record is not first_record


def test_runner_normalizes_evaluated_at_to_utc() -> None:
    """評価時刻をUTCへ正規化してFactoryへ渡す。"""

    jst = timezone(timedelta(hours=9))
    evaluated_at = datetime(
        2026,
        7,
        19,
        18,
        0,
        tzinfo=jst,
    )
    factory = FakeRequestFactory()
    runner = RiskEngineRunner(
        risk_engine=FakeRiskEngine(
            (
                FakeRiskResult(
                    allows_new_entries=True,
                    approved_quantity=100,
                ),
            )
        ),
        request_factory=factory,
    )

    record = runner.run(
        cycle_result=object(),
        portfolio_snapshot=create_snapshot(),
        evaluated_at=evaluated_at,
    )

    assert record.evaluated_at == EVALUATED_AT
    assert factory.calls[0]["evaluated_at"] == EVALUATED_AT


def test_runner_rejects_naive_evaluated_at() -> None:
    """タイムゾーンなし評価時刻を拒否する。"""

    runner = RiskEngineRunner(
        risk_engine=FakeRiskEngine(()),
        request_factory=FakeRequestFactory(),
    )

    with pytest.raises(
        ValueError,
        match="評価時刻にはタイムゾーンが必要です。",
    ):
        runner.run(
            cycle_result=object(),
            portfolio_snapshot=create_snapshot(),
            evaluated_at=datetime(
                2026,
                7,
                19,
                9,
                0,
            ),
        )


def test_allows_new_entries_runs_engine() -> None:
    """補助メソッドもRisk Engineを1回実行する。"""

    runner = RiskEngineRunner(
        risk_engine=FakeRiskEngine(
            (
                FakeRiskResult(
                    allows_new_entries=True,
                    approved_quantity=100,
                ),
            )
        ),
        request_factory=FakeRequestFactory(),
    )

    allowed = runner.allows_new_entries(
        cycle_result=object(),
        portfolio_snapshot=create_snapshot(),
        evaluated_at=EVALUATED_AT,
    )

    assert allowed
    assert runner.run_count == 1
    assert runner.last_record is not None
