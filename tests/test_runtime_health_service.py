"""RuntimeHealthServiceのテスト。"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pytest

from app.runtime.paper_trading_runtime_models import (
    PaperTradingRuntimeStatus,
)
from app.runtime.runtime_health_models import (
    RuntimeHealthStatus,
)
from app.runtime.runtime_health_service import (
    RuntimeHealthService,
)


NOW = datetime(
    2026,
    7,
    19,
    0,
    0,
    tzinfo=timezone.utc,
)


class FakeRuntime:
    """状態を差し替え可能なRuntime。"""

    def __init__(
        self,
        status: PaperTradingRuntimeStatus | None,
    ) -> None:
        self._status = status

    @property
    def status(
        self,
    ) -> PaperTradingRuntimeStatus | None:
        return self._status


class FailingRuntime:
    """状態取得時に失敗するRuntime。"""

    @property
    def status(self):
        raise RuntimeError("runtime unavailable")


@dataclass
class FakeSnapshot:
    """Portfolio診断用Snapshot。"""

    broker_equity: float = 1_000_000.0
    cash_balance: float = 800_000.0
    buying_power: float = 800_000.0


class FakePortfolioReader:
    """固定Snapshotを返すPortfolio Reader。"""

    def __init__(
        self,
        snapshot: FakeSnapshot,
    ) -> None:
        self.snapshot = snapshot
        self.generated_at: datetime | None = None

    def create_snapshot(
        self,
        *,
        generated_at: datetime | None = None,
    ) -> FakeSnapshot:
        self.generated_at = generated_at
        return self.snapshot


class FailingPortfolioReader:
    """Snapshot取得時に失敗するReader。"""

    def create_snapshot(
        self,
        *,
        generated_at: datetime | None = None,
    ):
        raise RuntimeError("portfolio unavailable")


def test_check_returns_ok_when_all_components_are_healthy() -> None:
    """全項目正常ならOKレポートを返す。"""

    repository_calls: list[str] = []
    portfolio_reader = FakePortfolioReader(
        FakeSnapshot()
    )

    service = RuntimeHealthService(
        runtime=FakeRuntime(
            PaperTradingRuntimeStatus.RUNNING
        ),
        portfolio_reader=portfolio_reader,
        broker_probe=lambda: {"cash": 800_000},
        repository_probes=(
            (
                "orders",
                lambda: repository_calls.append("orders"),
            ),
            (
                "positions",
                lambda: repository_calls.append(
                    "positions"
                ),
            ),
        ),
        market_data_time_provider=lambda: (
            NOW - timedelta(minutes=1)
        ),
        now_provider=lambda: NOW,
    )

    report = service.check()

    assert report.status is RuntimeHealthStatus.OK
    assert report.is_healthy
    assert not report.requires_attention
    assert tuple(
        check.name
        for check in report.checks
    ) == (
        "runtime",
        "portfolio",
        "broker",
        "repository",
        "market_data",
    )
    assert repository_calls == [
        "orders",
        "positions",
    ]
    assert portfolio_reader.generated_at == NOW


@pytest.mark.parametrize(
    ("runtime_status", "expected_status"),
    (
        (
            None,
            RuntimeHealthStatus.WARNING,
        ),
        (
            PaperTradingRuntimeStatus.RUNNING,
            RuntimeHealthStatus.OK,
        ),
        (
            PaperTradingRuntimeStatus.COMPLETED,
            RuntimeHealthStatus.WARNING,
        ),
        (
            PaperTradingRuntimeStatus.FAILED,
            RuntimeHealthStatus.ERROR,
        ),
    ),
)
def test_runtime_status_is_mapped_to_health_status(
    runtime_status,
    expected_status,
) -> None:
    """Runtime状態をHealth状態へ変換する。"""

    report = RuntimeHealthService(
        runtime=FakeRuntime(runtime_status),
        now_provider=lambda: NOW,
    ).check()

    check = report.get_check("runtime")

    assert check is not None
    assert check.status is expected_status
    assert report.status is expected_status


def test_runtime_exception_is_converted_to_error_check() -> None:
    """Runtime状態取得例外をERROR結果へ変換する。"""

    report = RuntimeHealthService(
        runtime=FailingRuntime(),
        now_provider=lambda: NOW,
    ).check()

    check = report.get_check("runtime")

    assert check is not None
    assert check.status is RuntimeHealthStatus.ERROR
    assert check.details["error_type"] == "RuntimeError"
    assert (
        check.details["error_message"]
        == "runtime unavailable"
    )


def test_portfolio_negative_balance_is_error() -> None:
    """Portfolioに負の残高があればERRORにする。"""

    report = RuntimeHealthService(
        portfolio_reader=FakePortfolioReader(
            FakeSnapshot(
                broker_equity=1_000_000.0,
                cash_balance=-1.0,
                buying_power=100_000.0,
            )
        ),
        now_provider=lambda: NOW,
    ).check()

    check = report.get_check("portfolio")

    assert check is not None
    assert check.status is RuntimeHealthStatus.ERROR
    assert check.details["cash_balance"] == -1.0


def test_portfolio_non_finite_value_is_error() -> None:
    """Portfolioに非有限値があればERRORにする。"""

    report = RuntimeHealthService(
        portfolio_reader=FakePortfolioReader(
            FakeSnapshot(
                broker_equity=float("nan"),
            )
        ),
        now_provider=lambda: NOW,
    ).check()

    check = report.get_check("portfolio")

    assert check is not None
    assert check.status is RuntimeHealthStatus.ERROR


def test_portfolio_exception_is_converted_to_error_check() -> None:
    """Portfolio取得例外をERROR結果へ変換する。"""

    report = RuntimeHealthService(
        portfolio_reader=FailingPortfolioReader(),
        now_provider=lambda: NOW,
    ).check()

    check = report.get_check("portfolio")

    assert check is not None
    assert check.status is RuntimeHealthStatus.ERROR
    assert check.details["error_type"] == "RuntimeError"


def test_broker_probe_exception_is_error() -> None:
    """Broker疎通確認例外をERROR結果へ変換する。"""

    def failing_probe():
        raise ConnectionError("broker offline")

    report = RuntimeHealthService(
        broker_probe=failing_probe,
        now_provider=lambda: NOW,
    ).check()

    check = report.get_check("broker")

    assert check is not None
    assert check.status is RuntimeHealthStatus.ERROR
    assert check.details["error_type"] == "ConnectionError"


def test_repository_failure_marks_repository_check_as_error() -> None:
    """1件でもRepository診断に失敗すればERRORにする。"""

    def failing_probe():
        raise RuntimeError("database locked")

    report = RuntimeHealthService(
        repository_probes=(
            ("orders", lambda: 1),
            ("executions", failing_probe),
        ),
        now_provider=lambda: NOW,
    ).check()

    check = report.get_check("repository")

    assert check is not None
    assert check.status is RuntimeHealthStatus.ERROR
    assert check.details["successful"] == ("orders",)
    assert "executions" in check.details["failed"]
    assert (
        "database locked"
        in check.details["failed"]["executions"]
    )


@pytest.mark.parametrize(
    ("last_updated_at", "expected_status"),
    (
        (
            None,
            RuntimeHealthStatus.WARNING,
        ),
        (
            NOW - timedelta(minutes=1),
            RuntimeHealthStatus.OK,
        ),
        (
            NOW - timedelta(minutes=5),
            RuntimeHealthStatus.WARNING,
        ),
        (
            NOW - timedelta(minutes=15),
            RuntimeHealthStatus.ERROR,
        ),
        (
            NOW + timedelta(seconds=1),
            RuntimeHealthStatus.WARNING,
        ),
    ),
)
def test_market_data_age_is_evaluated(
    last_updated_at,
    expected_status,
) -> None:
    """Market Data経過時間を閾値に沿って評価する。"""

    report = RuntimeHealthService(
        market_data_time_provider=lambda: (
            last_updated_at
        ),
        market_data_warning_after=timedelta(
            minutes=5
        ),
        market_data_error_after=timedelta(
            minutes=15
        ),
        now_provider=lambda: NOW,
    ).check()

    check = report.get_check("market_data")

    assert check is not None
    assert check.status is expected_status


def test_market_data_naive_datetime_is_error() -> None:
    """タイムゾーンなし更新日時をERRORにする。"""

    report = RuntimeHealthService(
        market_data_time_provider=lambda: datetime(
            2026,
            7,
            19,
            0,
            0,
        ),
        now_provider=lambda: NOW,
    ).check()

    check = report.get_check("market_data")

    assert check is not None
    assert check.status is RuntimeHealthStatus.ERROR


def test_worst_check_determines_report_status() -> None:
    """最も重大な個別結果を全体状態に採用する。"""

    report = RuntimeHealthService(
        runtime=FakeRuntime(
            PaperTradingRuntimeStatus.COMPLETED
        ),
        broker_probe=lambda: (_ for _ in ()).throw(
            RuntimeError("offline")
        ),
        market_data_time_provider=lambda: (
            NOW - timedelta(minutes=1)
        ),
        now_provider=lambda: NOW,
    ).check()

    assert report.status is RuntimeHealthStatus.ERROR
    assert tuple(
        check.name
        for check in report.failed_checks
    ) == ("broker",)
    assert tuple(
        check.name
        for check in report.warning_checks
    ) == ("runtime",)


def test_empty_configuration_returns_empty_ok_report() -> None:
    """診断対象なしでも空のOKレポートを返す。"""

    report = RuntimeHealthService(
        now_provider=lambda: NOW,
    ).check()

    assert report.status is RuntimeHealthStatus.OK
    assert report.checks == ()


def test_constructor_rejects_invalid_market_data_thresholds() -> None:
    """不正なMarket Data閾値を拒否する。"""

    with pytest.raises(ValueError, match="警告閾値"):
        RuntimeHealthService(
            market_data_warning_after=timedelta(0)
        )

    with pytest.raises(ValueError, match="エラー閾値"):
        RuntimeHealthService(
            market_data_warning_after=timedelta(
                minutes=5
            ),
            market_data_error_after=timedelta(
                minutes=5
            ),
        )


def test_constructor_rejects_duplicate_repository_names() -> None:
    """重複したRepository診断名を拒否する。"""

    with pytest.raises(ValueError, match="重複"):
        RuntimeHealthService(
            repository_probes=(
                ("orders", lambda: None),
                ("orders", lambda: None),
            )
        )


def test_check_rejects_naive_clock() -> None:
    """タイムゾーンなし現在日時を拒否する。"""

    service = RuntimeHealthService(
        now_provider=lambda: datetime(
            2026,
            7,
            19,
            0,
            0,
        )
    )

    with pytest.raises(ValueError, match="タイムゾーン"):
        service.check()
