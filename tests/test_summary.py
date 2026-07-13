"""株価集計機能のテスト。"""

from datetime import datetime

from app.market.models import StockPrice
from app.market.summary import summarize_prices


def test_summarize_prices() -> None:
    """株価データを正しく集計できる。"""

    prices = [
        StockPrice(
            code="7203",
            datetime=datetime(2026, 7, 13, 9, 0),
            open=3500.0,
            high=3520.0,
            low=3490.0,
            close=3510.0,
            volume=1_000,
        ),
        StockPrice(
            code="7203",
            datetime=datetime(2026, 7, 13, 9, 5),
            open=3510.0,
            high=3540.0,
            low=3505.0,
            close=3535.0,
            volume=2_000,
        ),
    ]

    summary = summarize_prices(prices)

    assert summary.record_count == 2
    assert summary.latest_close == 3535.0
    assert summary.total_volume == 3_000
    assert summary.highest_price == 3540.0
    assert summary.lowest_price == 3490.0
