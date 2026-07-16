"""ORBシグナル生成・保存サービスのテスト。"""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.database import initialize_database
from app.market.models import StockPrice
from app.strategy.opening_range_breakout import (
    OpeningRangeBreakoutStrategy,
)
from app.strategy.orb_diagnostics import (
    OrbDiagnosticService,
)
from app.trading.orb_signal_factory import (
    OrbSignalFactory,
    OrbSignalFactorySettings,
)
from app.trading.orb_signal_service import (
    OrbSignalGenerationService,
)
from app.trading.signal_models import (
    SignalAction,
    SignalStatus,
)
from app.trading.signal_repository import (
    SignalRepository,
)


CREATED_AT = datetime(
    2026,
    7,
    16,
    1,
    0,
    tzinfo=timezone.utc,
)


def create_price(
    code: str,
    time_text: str,
    *,
    high: float,
    low: float,
    close: float,
    volume: int,
) -> StockPrice:
    """サービス用の5分足を作成する。"""

    return StockPrice(
        code=code,
        datetime=datetime.strptime(
            f"2026-07-16 {time_text}",
            "%Y-%m-%d %H:%M",
        ),
        open=close,
        high=high,
        low=low,
        close=close,
        volume=volume,
    )


def create_candidate_prices(
    code: str,
) -> list[StockPrice]:
    """ORB候補になる1日分の5分足を作成する。"""

    return [
        create_price(
            code,
            "09:00",
            high=1005.0,
            low=995.0,
            close=1000.0,
            volume=100_000,
        ),
        create_price(
            code,
            "09:15",
            high=1010.0,
            low=998.0,
            close=1005.0,
            volume=100_000,
        ),
        create_price(
            code,
            "09:20",
            high=1020.0,
            low=1008.0,
            close=1015.0,
            volume=200_000,
        ),
        create_price(
            code,
            "14:50",
            high=1025.0,
            low=1010.0,
            close=1020.0,
            volume=300_000,
        ),
    ]


def create_rejected_prices(
    code: str,
) -> list[StockPrice]:
    """価格ブレイクしない1日分の5分足を作成する。"""

    return [
        create_price(
            code,
            "09:00",
            high=1005.0,
            low=995.0,
            close=1000.0,
            volume=100_000,
        ),
        create_price(
            code,
            "09:15",
            high=1010.0,
            low=998.0,
            close=1005.0,
            volume=100_000,
        ),
        create_price(
            code,
            "09:20",
            high=1010.0,
            low=1000.0,
            close=1008.0,
            volume=200_000,
        ),
        create_price(
            code,
            "14:50",
            high=1009.0,
            low=1000.0,
            close=1005.0,
            volume=300_000,
        ),
    ]


def create_strategy() -> OpeningRangeBreakoutStrategy:
    """サービス用ORB戦略を作成する。"""

    return OpeningRangeBreakoutStrategy(
        quantity=100,
        min_opening_range_volume=200_000,
        min_breakout_volume=150_000,
        breakout_volume_ratio=1.2,
        min_price=500.0,
        max_price=20_000.0,
        min_opening_range_turnover=(
            100_000_000.0
        ),
        min_breakout_turnover=(
            100_000_000.0
        ),
    )


def create_service(
    tmp_path: Path,
) -> tuple[
    SignalRepository,
    OrbSignalGenerationService,
]:
    """実SQLiteを使用するサービスを作成する。"""

    database_path = (
        tmp_path / "katana.db"
    )

    initialize_database(
        database_path
    )

    repository = SignalRepository(
        database_path,
        now_provider=lambda: CREATED_AT,
    )

    service = OrbSignalGenerationService(
        diagnostic_service=(
            OrbDiagnosticService(
                create_strategy()
            )
        ),
        signal_factory=(
            OrbSignalFactory(
                settings=(
                    OrbSignalFactorySettings(
                        strategy_name="orb",
                        quantity=100,
                        confidence=0.8,
                    )
                )
            )
        ),
        signal_repository=repository,
    )

    return repository, service


def test_service_generates_and_saves_candidate_signal(
    tmp_path: Path,
) -> None:
    """ORB候補を生成してPENDING保存する。"""

    repository, service = create_service(
        tmp_path
    )

    result = service.run(
        create_candidate_prices(
            "7203"
        )
    )

    assert result.diagnostic_count == 1
    assert result.candidate_count == 1
    assert result.generated_count == 1
    assert result.saved_count == 1
    assert result.duplicate_count == 0
    assert result.failed_count == 0
    assert result.is_successful is True

    record = result.saved_records[0]

    assert record.code == "7203"
    assert record.strategy_name == "orb"
    assert record.action is SignalAction.BUY
    assert record.status is SignalStatus.PENDING
    assert record.signal.signal_price == pytest.approx(
        1015.0
    )
    assert record.signal.quantity == 100
    assert record.signal.confidence == pytest.approx(
        0.8
    )

    assert repository.count() == 1
    assert repository.count(
        status=SignalStatus.PENDING
    ) == 1


def test_service_does_not_save_rejected_diagnostic(
    tmp_path: Path,
) -> None:
    """ORB候補でない診断結果は保存しない。"""

    repository, service = create_service(
        tmp_path
    )

    result = service.run(
        create_rejected_prices(
            "7203"
        )
    )

    assert result.diagnostic_count == 1
    assert result.candidate_count == 0
    assert result.generated_count == 0
    assert result.saved_count == 0
    assert result.duplicate_count == 0
    assert result.failed_count == 0
    assert repository.count() == 0


def test_service_saves_multiple_candidate_codes(
    tmp_path: Path,
) -> None:
    """複数銘柄の候補をそれぞれ保存する。"""

    repository, service = create_service(
        tmp_path
    )

    prices = [
        *create_candidate_prices(
            "7203"
        ),
        *create_candidate_prices(
            "8306"
        ),
    ]

    result = service.run(
        prices
    )

    assert result.diagnostic_count == 2
    assert result.candidate_count == 2
    assert result.generated_count == 2
    assert result.saved_count == 2
    assert repository.count() == 2

    assert {
        record.code
        for record in result.saved_records
    } == {
        "7203",
        "8306",
    }


def test_service_skips_duplicate_signals(
    tmp_path: Path,
) -> None:
    """同じ市場データの再実行では重複保存しない。"""

    repository, service = create_service(
        tmp_path
    )

    prices = create_candidate_prices(
        "7203"
    )

    first_result = service.run(
        prices
    )
    second_result = service.run(
        prices
    )

    assert first_result.saved_count == 1
    assert first_result.duplicate_count == 0

    assert second_result.generated_count == 1
    assert second_result.saved_count == 0
    assert second_result.duplicate_count == 1
    assert second_result.failed_count == 0
    assert second_result.is_successful is True

    assert repository.count() == 1


def test_service_combines_candidates_and_rejections(
    tmp_path: Path,
) -> None:
    """候補銘柄だけを保存し、除外銘柄は診断に残す。"""

    repository, service = create_service(
        tmp_path
    )

    prices = [
        *create_candidate_prices(
            "7203"
        ),
        *create_rejected_prices(
            "8306"
        ),
    ]

    result = service.run(
        prices
    )

    assert result.diagnostic_count == 2
    assert result.candidate_count == 1
    assert result.generated_count == 1
    assert result.saved_count == 1

    assert (
        result.saved_records[0].code
        == "7203"
    )
    assert repository.count() == 1


class FailingSignalRepository:
    """常に保存エラーを発生させるRepository。"""

    def save(
        self,
        signal,
    ):
        """保存失敗を発生させる。"""

        raise RuntimeError(
            f"save failed: {signal.signal_id}"
        )


def create_failing_service() -> OrbSignalGenerationService:
    """保存失敗用サービスを作成する。"""

    return OrbSignalGenerationService(
        diagnostic_service=(
            OrbDiagnosticService(
                create_strategy()
            )
        ),
        signal_factory=(
            OrbSignalFactory()
        ),
        signal_repository=(
            FailingSignalRepository()
        ),
    )


def test_service_records_save_failure() -> None:
    """continue_on_error有効時は保存失敗を記録する。"""

    service = create_failing_service()

    result = service.run(
        create_candidate_prices(
            "7203"
        ),
        continue_on_error=True,
    )

    assert result.generated_count == 1
    assert result.saved_count == 0
    assert result.failed_count == 1
    assert result.is_successful is False

    failure = result.failures[0]

    assert failure.code == "7203"
    assert "save failed" in failure.message


def test_service_raises_save_failure_when_continuation_disabled() -> None:
    """continue_on_error無効時は保存例外を再送出する。"""

    service = create_failing_service()

    with pytest.raises(
        RuntimeError,
        match="save failed",
    ):
        service.run(
            create_candidate_prices(
                "7203"
            ),
            continue_on_error=False,
        )


def test_service_handles_empty_prices(
    tmp_path: Path,
) -> None:
    """価格データが空なら空の正常結果を返す。"""

    repository, service = create_service(
        tmp_path
    )

    result = service.run(
        []
    )

    assert result.diagnostic_count == 0
    assert result.candidate_count == 0
    assert result.generated_count == 0
    assert result.saved_count == 0
    assert result.duplicate_count == 0
    assert result.failed_count == 0
    assert result.is_successful is True
    assert repository.count() == 0