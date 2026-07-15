"""ORB診断機能のテスト。"""

from datetime import datetime, time

from app.market.models import StockPrice
from app.strategy.opening_range_breakout import (
    OpeningRangeBreakoutStrategy,
)
from app.strategy.orb_diagnostics import (
    OrbDiagnosticService,
)


def create_price(
    time_text: str,
    *,
    high: float,
    low: float,
    close: float,
    volume: int,
) -> StockPrice:
    """診断用の5分足を作成する。"""

    return StockPrice(
        code="7203",
        datetime=datetime.strptime(
            f"2026-07-13 {time_text}",
            "%Y-%m-%d %H:%M",
        ),
        open=close,
        high=high,
        low=low,
        close=close,
        volume=volume,
    )


def create_strategy(
    **overrides: object,
) -> OpeningRangeBreakoutStrategy:
    """診断用戦略を作成する。"""

    arguments: dict[str, object] = {
        "opening_range_end": time(9, 15),
        "force_exit_time": time(14, 50),
        "min_opening_range_volume": 200_000,
        "min_breakout_volume": 150_000,
        "breakout_volume_ratio": 1.2,
        "min_price": 500.0,
        "max_price": 20_000.0,
        "min_opening_range_turnover": 100_000_000.0,
        "min_breakout_turnover": 100_000_000.0,
    }
    arguments.update(overrides)

    return OpeningRangeBreakoutStrategy(**arguments)


def create_prices(
    *,
    opening_volume: int = 100_000,
    breakout_volume: int = 200_000,
    breakout_high: float = 1020.0,
    breakout_close: float = 1015.0,
) -> list[StockPrice]:
    """標準的なORB候補データを作成する。"""

    return [
        create_price(
            "09:00",
            high=1005.0,
            low=995.0,
            close=1000.0,
            volume=opening_volume,
        ),
        create_price(
            "09:15",
            high=1010.0,
            low=998.0,
            close=1005.0,
            volume=opening_volume,
        ),
        create_price(
            "09:20",
            high=breakout_high,
            low=1008.0,
            close=breakout_close,
            volume=breakout_volume,
        ),
        create_price(
            "14:50",
            high=1025.0,
            low=1010.0,
            close=1020.0,
            volume=300_000,
        ),
    ]


def diagnose(
    strategy: OpeningRangeBreakoutStrategy,
    prices: list[StockPrice],
):
    """1日分を診断する。"""

    report = OrbDiagnosticService(strategy).run(prices)

    return report.daily_results[0]


def test_diagnostic_accepts_trade_candidate() -> None:
    """すべての条件を通過した候補を判定する。"""

    result = diagnose(
        create_strategy(),
        create_prices(),
    )

    assert result.price_breakout_found
    assert result.breakout_volume_passed
    assert result.breakout_volume_ratio_passed
    assert result.breakout_turnover_passed
    assert result.price_range_passed
    assert result.exit_available
    assert result.trade_candidate
    assert result.rejection_reason == ""


def test_diagnostic_identifies_opening_volume() -> None:
    """寄り付き出来高不足を特定する。"""

    result = diagnose(
        create_strategy(
            min_opening_range_volume=300_000,
        ),
        create_prices(
            opening_volume=100_000,
        ),
    )

    assert not result.trade_candidate
    assert result.rejection_reason == ("opening_volume")


def test_diagnostic_identifies_opening_turnover() -> None:
    """寄り付き売買代金不足を特定する。"""

    result = diagnose(
        create_strategy(
            min_opening_range_turnover=300_000_000.0,
        ),
        create_prices(
            opening_volume=100_000,
        ),
    )

    assert result.opening_volume_passed
    assert not result.opening_turnover_passed
    assert not result.trade_candidate
    assert result.rejection_reason == ("opening_turnover")


def test_diagnostic_identifies_no_price_breakout() -> None:
    """価格ブレイクがないことを特定する。"""

    result = diagnose(
        create_strategy(),
        create_prices(
            breakout_high=1010.0,
            breakout_close=1008.0,
        ),
    )

    assert not result.price_breakout_found
    assert not result.trade_candidate
    assert result.rejection_reason == ("no_price_breakout")


def test_diagnostic_identifies_breakout_volume() -> None:
    """ブレイク足出来高不足を特定する。"""

    result = diagnose(
        create_strategy(),
        create_prices(
            breakout_volume=100_000,
        ),
    )

    assert result.price_breakout_found
    assert not result.breakout_volume_passed
    assert not result.trade_candidate
    assert result.rejection_reason == ("breakout_volume")


def test_diagnostic_identifies_volume_ratio() -> None:
    """出来高倍率不足を特定する。"""

    result = diagnose(
        create_strategy(
            min_breakout_volume=None,
            breakout_volume_ratio=2.0,
        ),
        create_prices(
            opening_volume=100_000,
            breakout_volume=150_000,
        ),
    )

    assert result.breakout_volume_passed
    assert not result.breakout_volume_ratio_passed
    assert not result.trade_candidate
    assert result.rejection_reason == ("breakout_volume_ratio")


def test_diagnostic_identifies_breakout_turnover() -> None:
    """ブレイク足売買代金不足を特定する。"""

    result = diagnose(
        create_strategy(
            min_breakout_turnover=300_000_000.0,
        ),
        create_prices(),
    )

    assert result.breakout_volume_passed
    assert result.breakout_volume_ratio_passed
    assert not result.breakout_turnover_passed
    assert not result.trade_candidate
    assert result.rejection_reason == ("breakout_turnover")


def test_diagnostic_identifies_price_range() -> None:
    """株価帯条件の不一致を特定する。"""

    result = diagnose(
        create_strategy(
            min_price=2000.0,
        ),
        create_prices(),
    )

    assert result.breakout_turnover_passed
    assert not result.price_range_passed
    assert not result.trade_candidate
    assert result.rejection_reason == ("price_range")


def test_diagnostic_identifies_exit_unavailable() -> None:
    """ブレイク後の決済足不足を特定する。"""

    prices = create_prices()[:3]

    result = diagnose(
        create_strategy(),
        prices,
    )

    assert result.price_breakout_found
    assert result.breakout_volume_passed
    assert result.breakout_volume_ratio_passed
    assert result.breakout_turnover_passed
    assert result.price_range_passed
    assert not result.exit_available
    assert not result.trade_candidate
    assert result.rejection_reason == ("exit_unavailable")


def test_diagnostic_uses_later_valid_breakout() -> None:
    """最初の突破足が失格でも後続の有効足を使う。"""

    prices = [
        *create_prices()[:2],
        create_price(
            "09:20",
            high=1020.0,
            low=1008.0,
            close=1015.0,
            volume=50_000,
        ),
        create_price(
            "09:25",
            high=1025.0,
            low=1010.0,
            close=1020.0,
            volume=250_000,
        ),
        create_price(
            "14:50",
            high=1030.0,
            low=1015.0,
            close=1025.0,
            volume=300_000,
        ),
    ]

    result = diagnose(
        create_strategy(),
        prices,
    )

    assert result.trade_candidate
    assert result.breakout_at == datetime(
        2026,
        7,
        13,
        9,
        25,
    )
    assert result.rejection_reason == ""


def test_diagnostic_creates_symbol_summary() -> None:
    """日次診断結果を銘柄別に集計する。"""

    report = OrbDiagnosticService(create_strategy()).run(create_prices())

    assert report.symbol_count == 1
    assert report.trading_day_count == 1
    assert report.trade_candidate_count == 1

    summary = report.symbol_summaries[0]

    assert summary.code == "7203"
    assert summary.trading_day_count == 1
    assert summary.opening_range_count == 1
    assert summary.opening_volume_pass_count == 1
    assert summary.opening_turnover_pass_count == 1
    assert summary.price_breakout_count == 1
    assert summary.breakout_volume_pass_count == 1
    assert summary.breakout_volume_ratio_pass_count == 1
    assert summary.breakout_turnover_pass_count == 1
    assert summary.price_range_pass_count == 1
    assert summary.exit_available_count == 1
    assert summary.trade_candidate_count == 1
