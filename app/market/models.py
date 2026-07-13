"""株価データモデル。"""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class StockPrice:
    """1本のローソク足を表す。"""

    code: str
    datetime: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int

    def __post_init__(self) -> None:
        """不正なローソク足データを拒否する。"""

        if not self.code:
            raise ValueError("銘柄コードを指定してください。")

        prices = {
            "始値": self.open,
            "高値": self.high,
            "安値": self.low,
            "終値": self.close,
        }

        for name, value in prices.items():
            if value <= 0:
                raise ValueError(f"{name}は0より大きい必要があります。")

        if self.high < max(self.open, self.close, self.low):
            raise ValueError("高値が他の価格より低くなっています。")

        if self.low > min(self.open, self.close, self.high):
            raise ValueError("安値が他の価格より高くなっています。")

        if self.volume < 0:
            raise ValueError("出来高は0以上である必要があります。")
