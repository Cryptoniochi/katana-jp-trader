"""RiskEngineの統合テスト。"""

from datetime import date, datetime, timezone

import pytest

from app.risk.consecutive_loss_models import (
    ConsecutiveLossPolicy,
    ConsecutiveLossSnapshot,
)
from app.risk.consecutive_loss_service import ConsecutiveLossService
from app.risk.daily_loss_models import (
    DailyLossPolicy,
    DailyLossSnapshot,
)
from app.risk.daily_loss_service import DailyLossService
from app.risk.kill_switch_service import KillSwitchService
from app.risk.position_sizing_models import (
    PositionSizingPolicy,
    PositionSizingRequest,
    PositionSizingStatus,
)
from app.risk.position_sizing_service import PositionSizingService
from app.risk.risk_engine import (
    RiskEngine,
    RiskEngineRequest,
)
from app.risk.risk_report_models import (
    RiskReportReason,
    RiskReportStatus,
)
from app.risk.risk_report_service import RiskReportService


TRADING_DATE = date(2026, 7, 19)
EVALUATED_AT = datetime(
    2026,
    7,
    19,
    9,
    0,
    tzinfo=timezone.utc,
)


@pytest.fixture
def engine() -> RiskEngine:
    """標準設定のRiskEngineを返す。"""

    return RiskEngine(
        position_sizing_service=PositionSizingService(
            policy=PositionSizingPolicy(
                max_position_count=5,
                max_position_value=500_000.0,
                max_order_value=300_000.0,
                max_portfolio_exposure=1_500_000.0,
                lot_size=100,
            )
        ),
        daily_loss_service=DailyLossService(
            policy=DailyLossPolicy(
                max_daily_loss=100_000.0,
                warning_ratio=0.8,
            )
        ),
        consecutive_loss_service=ConsecutiveLossService(
            policy=ConsecutiveLossPolicy(
                max_consecutive_losses=3,
                warning_consecutive_losses=2,
            )
        ),
        kill_switch_service=KillSwitchService(),
        risk_report_service=RiskReportService(),
    )


def make_position_request(
    *,
    price: float = 1_000.0,
    requested_quantity: int = 200,
    current_position_quantity: int = 0,
    current_position_count: int = 0,
    current_portfolio_exposure: float = 0.0,
    buying_power: float = 1_000_000.0,
) -> PositionSizingRequest:
    """PositionSizingRequestを生成する。"""

    return PositionSizingRequest(
        code="7203",
        price=price,
        requested_quantity=requested_quantity,
        current_position_quantity=current_position_quantity,
        current_position_count=current_position_count,
        current_portfolio_exposure=current_portfolio_exposure,
        buying_power=buying_power,
    )


def make_request(
    *,
    position_sizing_request: PositionSizingRequest | None = None,
    realized_pnl: float = 0.0,
    unrealized_pnl: float = 0.0,
    consecutive_losses: int = 0,
    last_trade_pnl: float | None = None,
    manual_blocked: bool = False,
    runtime_health_ok: bool = True,
    heartbeat_alive: bool = True,
    broker_available: bool = True,
    trading_date: date = TRADING_DATE,
    evaluated_at: datetime = EVALUATED_AT,
) -> RiskEngineRequest:
    """RiskEngineRequestを生成する。"""

    return RiskEngineRequest(
        trading_date=trading_date,
        position_sizing_request=(
            position_sizing_request
            if position_sizing_request is not None
            else make_position_request()
        ),
        daily_loss_snapshot=DailyLossSnapshot(
            trading_date=trading_date,
            realized_pnl=realized_pnl,
            unrealized_pnl=unrealized_pnl,
            evaluated_at=evaluated_at,
        ),
        consecutive_loss_snapshot=ConsecutiveLossSnapshot(
            trading_date=trading_date,
            consecutive_losses=consecutive_losses,
            last_trade_pnl=last_trade_pnl,
            evaluated_at=evaluated_at,
        ),
        manual_blocked=manual_blocked,
        runtime_health_ok=runtime_health_ok,
        heartbeat_alive=heartbeat_alive,
        broker_available=broker_available,
        evaluated_at=evaluated_at,
    )


def test_all_clear_approves_requested_quantity(
    engine: RiskEngine,
) -> None:
    """全リスク条件が正常なら注文数量を承認する。"""

    result = engine.evaluate(
        make_request()
    )

    assert result.position_sizing.status is PositionSizingStatus.APPROVED
    assert result.approved_quantity == 200
    assert result.risk_report.status is RiskReportStatus.CLEAR
    assert result.risk_report.primary_reason is RiskReportReason.ALL_CLEAR
    assert result.allows_new_entries
    assert not result.is_blocked


def test_position_size_reduction_produces_warning(
    engine: RiskEngine,
) -> None:
    """数量縮小時はWARNINGと縮小後数量を返す。"""

    result = engine.evaluate(
        make_request(
            position_sizing_request=make_position_request(
                requested_quantity=500,
            ),
        )
    )

    assert result.position_sizing.status is PositionSizingStatus.REDUCED
    assert result.position_sizing.approved_quantity == 300
    assert result.approved_quantity == 300
    assert result.risk_report.status is RiskReportStatus.WARNING
    assert (
        result.risk_report.primary_reason
        is RiskReportReason.POSITION_SIZE_REDUCED
    )
    assert result.allows_new_entries


def test_position_size_rejection_blocks_order(
    engine: RiskEngine,
) -> None:
    """Position Sizing拒否時は注文数量を0にする。"""

    result = engine.evaluate(
        make_request(
            position_sizing_request=make_position_request(
                requested_quantity=200,
                buying_power=50_000.0,
            ),
        )
    )

    assert result.position_sizing.status is PositionSizingStatus.REJECTED
    assert result.approved_quantity == 0
    assert result.risk_report.status is RiskReportStatus.BLOCKED
    assert (
        result.risk_report.primary_reason
        is RiskReportReason.POSITION_SIZE_REJECTED
    )
    assert result.is_blocked


def test_daily_loss_warning_does_not_block(
    engine: RiskEngine,
) -> None:
    """日次損失警告では新規エントリーを許可する。"""

    result = engine.evaluate(
        make_request(
            realized_pnl=-80_000.0,
        )
    )

    assert result.risk_report.status is RiskReportStatus.WARNING
    assert (
        RiskReportReason.DAILY_LOSS_WARNING
        in result.risk_report.warning_reasons
    )
    assert result.approved_quantity == 200
    assert result.allows_new_entries


def test_daily_loss_limit_blocks_order(
    engine: RiskEngine,
) -> None:
    """最大日次損失到達時は注文数量を0にする。"""

    result = engine.evaluate(
        make_request(
            realized_pnl=-100_000.0,
        )
    )

    assert result.daily_loss.is_blocked
    assert result.kill_switch.is_blocked
    assert result.approved_quantity == 0
    assert result.risk_report.status is RiskReportStatus.BLOCKED
    assert (
        RiskReportReason.DAILY_LOSS_BLOCKED
        in result.risk_report.blocking_reasons
    )
    assert (
        RiskReportReason.KILL_SWITCH_BLOCKED
        in result.risk_report.blocking_reasons
    )


def test_consecutive_loss_warning_does_not_block(
    engine: RiskEngine,
) -> None:
    """連敗警告では新規エントリーを許可する。"""

    result = engine.evaluate(
        make_request(
            consecutive_losses=2,
            last_trade_pnl=-10_000.0,
        )
    )

    assert result.risk_report.status is RiskReportStatus.WARNING
    assert (
        RiskReportReason.CONSECUTIVE_LOSS_WARNING
        in result.risk_report.warning_reasons
    )
    assert result.approved_quantity == 200


def test_consecutive_loss_limit_blocks_order(
    engine: RiskEngine,
) -> None:
    """最大連敗数到達時は注文数量を0にする。"""

    result = engine.evaluate(
        make_request(
            consecutive_losses=3,
            last_trade_pnl=-10_000.0,
        )
    )

    assert result.consecutive_loss.is_blocked
    assert result.kill_switch.is_blocked
    assert result.approved_quantity == 0
    assert (
        RiskReportReason.CONSECUTIVE_LOSS_BLOCKED
        in result.risk_report.blocking_reasons
    )


@pytest.mark.parametrize(
    (
        "request_kwargs",
        "expected_reason",
    ),
    (
        (
            {"manual_blocked": True},
            RiskReportReason.KILL_SWITCH_BLOCKED,
        ),
        (
            {"runtime_health_ok": False},
            RiskReportReason.RUNTIME_HEALTH_ERROR,
        ),
        (
            {"heartbeat_alive": False},
            RiskReportReason.HEARTBEAT_STALE,
        ),
        (
            {"broker_available": False},
            RiskReportReason.BROKER_UNAVAILABLE,
        ),
    ),
)
def test_operational_failure_blocks_order(
    engine: RiskEngine,
    request_kwargs: dict[str, bool],
    expected_reason: RiskReportReason,
) -> None:
    """各運用異常が注文を停止する。"""

    result = engine.evaluate(
        make_request(
            **request_kwargs,
        )
    )

    assert result.is_blocked
    assert result.approved_quantity == 0
    assert expected_reason in result.risk_report.blocking_reasons
    assert (
        RiskReportReason.KILL_SWITCH_BLOCKED
        in result.risk_report.blocking_reasons
    )


def test_multiple_warnings_are_all_reported(
    engine: RiskEngine,
) -> None:
    """複数の警告理由をすべてレポートへ保持する。"""

    result = engine.evaluate(
        make_request(
            position_sizing_request=make_position_request(
                requested_quantity=500,
            ),
            realized_pnl=-80_000.0,
            consecutive_losses=2,
        )
    )

    assert result.risk_report.status is RiskReportStatus.WARNING
    assert result.risk_report.warning_reasons == (
        RiskReportReason.POSITION_SIZE_REDUCED,
        RiskReportReason.DAILY_LOSS_WARNING,
        RiskReportReason.CONSECUTIVE_LOSS_WARNING,
    )


def test_report_contains_expected_item_order(
    engine: RiskEngine,
) -> None:
    """Risk Report項目の順序を固定する。"""

    result = engine.evaluate(
        make_request()
    )

    assert tuple(
        item.name
        for item in result.risk_report.items
    ) == (
        "position_sizing",
        "daily_loss",
        "consecutive_loss",
        "runtime_health",
        "heartbeat",
        "broker",
        "kill_switch",
    )


def test_report_metadata_contains_quantities(
    engine: RiskEngine,
) -> None:
    """統合レポートmetadataへ希望数量と承認数量を記録する。"""

    result = engine.evaluate(
        make_request(
            position_sizing_request=make_position_request(
                requested_quantity=500,
            ),
        )
    )

    assert result.risk_report.metadata == {
        "requested_quantity": 500,
        "approved_quantity": 300,
    }


def test_preserves_evaluated_at(
    engine: RiskEngine,
) -> None:
    """評価時刻をRisk Reportへ引き継ぐ。"""

    evaluated_at = datetime(
        2026,
        7,
        19,
        10,
        30,
        tzinfo=timezone.utc,
    )

    result = engine.evaluate(
        make_request(
            evaluated_at=evaluated_at,
        )
    )

    assert result.risk_report.generated_at == evaluated_at
    assert result.kill_switch.evaluated_at == evaluated_at


def test_normalizes_naive_evaluated_at_to_utc(
    engine: RiskEngine,
) -> None:
    """タイムゾーンなし評価時刻をUTCとして扱う。"""

    result = engine.evaluate(
        make_request(
            evaluated_at=datetime(
                2026,
                7,
                19,
                9,
                0,
            ),
        )
    )

    assert result.risk_report.generated_at.tzinfo is timezone.utc


def test_allows_new_entries_helper(
    engine: RiskEngine,
) -> None:
    """新規エントリー可否の補助メソッドを検証する。"""

    assert engine.allows_new_entries(
        make_request()
    )

    assert not engine.allows_new_entries(
        make_request(
            broker_available=False,
        )
    )


def test_rejects_mismatched_daily_loss_trading_date() -> None:
    """Daily Loss Snapshotの取引日不一致を拒否する。"""

    with pytest.raises(
        ValueError,
        match="daily_loss_snapshotのtrading_dateが一致しません。",
    ):
        RiskEngineRequest(
            trading_date=TRADING_DATE,
            position_sizing_request=make_position_request(),
            daily_loss_snapshot=DailyLossSnapshot(
                trading_date=date(2026, 7, 18),
                realized_pnl=0.0,
            ),
            consecutive_loss_snapshot=ConsecutiveLossSnapshot(
                trading_date=TRADING_DATE,
                consecutive_losses=0,
            ),
        )


def test_rejects_mismatched_consecutive_loss_trading_date() -> None:
    """Consecutive Loss Snapshotの取引日不一致を拒否する。"""

    with pytest.raises(
        ValueError,
        match=(
            "consecutive_loss_snapshotの"
            "trading_dateが一致しません。"
        ),
    ):
        RiskEngineRequest(
            trading_date=TRADING_DATE,
            position_sizing_request=make_position_request(),
            daily_loss_snapshot=DailyLossSnapshot(
                trading_date=TRADING_DATE,
                realized_pnl=0.0,
            ),
            consecutive_loss_snapshot=ConsecutiveLossSnapshot(
                trading_date=date(2026, 7, 18),
                consecutive_losses=0,
            ),
        )
