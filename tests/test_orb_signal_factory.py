"""ORB診断結果からのシグナル生成テスト。"""

from datetime import date, datetime, timezone

import pytest

from app.strategy.orb_diagnostics import (
    OrbDailyDiagnostic,
)
from app.trading.orb_signal_factory import (
    JAPAN_TIMEZONE,
    OrbSignalFactory,
    OrbSignalFactorySettings,
)
from app.trading.signal_models import (
    SignalAction,
)


BREAKOUT_AT = datetime(
    2026,
    7,
    16,
    9,
    20,
)


def create_diagnostic(
    *,
    code: str = "7203",
    trade_candidate: bool = True,
    rejection_reason: str = "",
    breakout_at: datetime | None = BREAKOUT_AT,
    breakout_price: float | None = 2500.0,
) -> OrbDailyDiagnostic:
    """テスト用ORB診断結果を作成する。"""

    return OrbDailyDiagnostic(
        code=code,
        trading_date=date(
            2026,
            7,
            16,
        ),
        bar_count=60,
        opening_bar_count=4,
        opening_range_high=2480.0,
        opening_range_volume=400_000,
        opening_range_turnover=990_000_000.0,
        average_opening_volume=100_000.0,
        opening_range_available=True,
        opening_volume_passed=True,
        opening_turnover_passed=True,
        price_breakout_found=True,
        breakout_at=breakout_at,
        breakout_price=breakout_price,
        breakout_volume=150_000,
        breakout_volume_ratio=1.5,
        breakout_turnover=375_000_000.0,
        breakout_volume_passed=True,
        breakout_volume_ratio_passed=True,
        breakout_turnover_passed=True,
        price_range_passed=True,
        exit_available=True,
        trade_candidate=trade_candidate,
        rejection_reason=rejection_reason,
    )


def test_factory_creates_buy_signal() -> None:
    """ORB候補からBUYシグナルを生成する。"""

    factory = OrbSignalFactory(
        settings=OrbSignalFactorySettings(
            strategy_name="orb",
            quantity=200,
            confidence=0.85,
        )
    )

    signal = factory.create(
        create_diagnostic()
    )

    assert signal is not None
    assert signal.code == "7203"
    assert signal.strategy_name == "orb"
    assert signal.action is SignalAction.BUY
    assert signal.generated_at == (
        BREAKOUT_AT.replace(
            tzinfo=JAPAN_TIMEZONE,
        )
    )
    assert signal.signal_price == pytest.approx(
        2500.0,
    )
    assert signal.quantity == 200
    assert signal.reason == (
        "opening_range_breakout"
    )
    assert signal.confidence == pytest.approx(
        0.85,
    )
    assert signal.signal_id.startswith(
        "orb-7203-"
    )


def test_factory_creates_orb_metadata() -> None:
    """診断情報をシグナルメタデータへ保存する。"""

    signal = OrbSignalFactory().create(
        create_diagnostic()
    )

    assert signal is not None

    assert signal.metadata[
        "trading_date"
    ] == "2026-07-16"
    assert signal.metadata[
        "opening_range_high"
    ] == pytest.approx(
        2480.0,
    )
    assert signal.metadata[
        "opening_range_volume"
    ] == 400_000
    assert signal.metadata[
        "breakout_volume"
    ] == 150_000
    assert signal.metadata[
        "breakout_volume_ratio"
    ] == pytest.approx(
        1.5,
    )
    assert signal.metadata[
        "trade_candidate"
    ] is True


def test_factory_returns_none_for_rejected_diagnostic() -> None:
    """ORB候補でない診断結果はシグナル化しない。"""

    factory = OrbSignalFactory()

    signal = factory.create(
        create_diagnostic(
            trade_candidate=False,
            rejection_reason=(
                "breakout_volume"
            ),
        )
    )

    assert signal is None


def test_factory_generates_deterministic_signal_id() -> None:
    """同じ診断結果から同じシグナルIDを生成する。"""

    factory = OrbSignalFactory()

    first_signal = factory.create(
        create_diagnostic()
    )
    second_signal = factory.create(
        create_diagnostic()
    )

    assert first_signal is not None
    assert second_signal is not None

    assert (
        first_signal.signal_id
        == second_signal.signal_id
    )


def test_factory_generates_different_ids_for_different_codes() -> None:
    """銘柄が異なれば別のシグナルIDを生成する。"""

    factory = OrbSignalFactory()

    first_signal = factory.create(
        create_diagnostic(
            code="7203",
        )
    )
    second_signal = factory.create(
        create_diagnostic(
            code="8306",
        )
    )

    assert first_signal is not None
    assert second_signal is not None
    assert (
        first_signal.signal_id
        != second_signal.signal_id
    )


def test_factory_accepts_timezone_aware_datetime() -> None:
    """タイムゾーン付き日時を日本時間へ変換する。"""

    utc_breakout_at = datetime(
        2026,
        7,
        16,
        0,
        20,
        tzinfo=timezone.utc,
    )

    signal = OrbSignalFactory().create(
        create_diagnostic(
            breakout_at=utc_breakout_at,
        )
    )

    assert signal is not None
    assert signal.generated_at == datetime(
        2026,
        7,
        16,
        9,
        20,
        tzinfo=JAPAN_TIMEZONE,
    )


def test_factory_create_many_filters_and_sorts() -> None:
    """候補だけをシグナル化して日時・銘柄順に返す。"""

    factory = OrbSignalFactory()

    diagnostics = [
        create_diagnostic(
            code="8306",
            breakout_at=datetime(
                2026,
                7,
                16,
                9,
                25,
            ),
        ),
        create_diagnostic(
            code="7203",
            trade_candidate=False,
            rejection_reason="price_range",
        ),
        create_diagnostic(
            code="6758",
            breakout_at=datetime(
                2026,
                7,
                16,
                9,
                20,
            ),
        ),
    ]

    signals = factory.create_many(
        diagnostics
    )

    assert [
        signal.code
        for signal in signals
    ] == [
        "6758",
        "8306",
    ]


def test_factory_rejects_candidate_with_rejection_reason() -> None:
    """候補と除外理由が同時設定された不整合を拒否する。"""

    factory = OrbSignalFactory()

    with pytest.raises(
        ValueError,
        match="除外理由",
    ):
        factory.create(
            create_diagnostic(
                trade_candidate=True,
                rejection_reason=(
                    "breakout_volume"
                ),
            )
        )


def test_factory_rejects_candidate_without_breakout_time() -> None:
    """候補にブレイク日時がなければ拒否する。"""

    factory = OrbSignalFactory()

    with pytest.raises(
        ValueError,
        match="ブレイク日時",
    ):
        factory.create(
            create_diagnostic(
                breakout_at=None,
            )
        )


def test_factory_rejects_candidate_without_breakout_price() -> None:
    """候補にブレイク価格がなければ拒否する。"""

    factory = OrbSignalFactory()

    with pytest.raises(
        ValueError,
        match="ブレイク価格",
    ):
        factory.create(
            create_diagnostic(
                breakout_price=None,
            )
        )


@pytest.mark.parametrize(
    (
        "arguments",
        "message",
    ),
    [
        (
            {
                "strategy_name": " ",
            },
            "戦略名",
        ),
        (
            {
                "quantity": 0,
            },
            "数量",
        ),
        (
            {
                "confidence": -0.1,
            },
            "信頼度",
        ),
        (
            {
                "confidence": 1.1,
            },
            "信頼度",
        ),
    ],
)
def test_factory_settings_reject_invalid_values(
    arguments: dict[str, object],
    message: str,
) -> None:
    """不正なシグナル生成設定を拒否する。"""

    with pytest.raises(
        ValueError,
        match=message,
    ):
        OrbSignalFactorySettings(
            **arguments,
        )