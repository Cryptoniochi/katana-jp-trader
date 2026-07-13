"""株価データモデル"""

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class StockPrice:
    """1本のローソク足"""

    code: str
    datetime: datetime

    open: float
    high: float
    low: float
    close: float

    volume: int
