"""バックテスト用注文キュー。"""

from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import Deque

from app.trading.order_models import TradeOrderRecord


@dataclass(frozen=True, slots=True)
class QueuedBacktestOrder:
    """バックテストキューへ登録された注文。"""

    order_record: TradeOrderRecord
    enqueued_at: datetime

    def __post_init__(self) -> None:
        """キュー登録情報を検証する。"""

        if self.enqueued_at.tzinfo is None:
            raise ValueError(
                "キュー登録日時にはタイムゾーンが必要です。"
            )

    @property
    def order_id(self) -> str:
        """注文IDを返す。"""

        return self.order_record.order_id

    @property
    def signal_id(self) -> str:
        """元シグナルIDを返す。"""

        return self.order_record.signal_id


class DuplicateQueuedOrderError(RuntimeError):
    """同じ注文IDが既にキューへ存在する。"""


class BacktestOrderQueue:
    """注文をFIFOで保持するインメモリキュー。"""

    def __init__(self) -> None:
        """空の注文キューを作成する。"""

        self._items: Deque[QueuedBacktestOrder] = deque()
        self._order_ids: set[str] = set()

    def enqueue(
        self,
        item: QueuedBacktestOrder,
    ) -> None:
        """注文をキュー末尾へ追加する。"""

        if item.order_id in self._order_ids:
            raise DuplicateQueuedOrderError(
                "同じ注文IDが既にキューへ存在します。 "
                f"order_id={item.order_id}"
            )

        self._items.append(item)
        self._order_ids.add(item.order_id)

    def peek(self) -> QueuedBacktestOrder | None:
        """先頭注文を削除せず返す。"""

        if not self._items:
            return None

        return self._items[0]

    def pop(self) -> QueuedBacktestOrder | None:
        """先頭注文を削除して返す。"""

        if not self._items:
            return None

        item = self._items.popleft()
        self._order_ids.remove(item.order_id)

        return item

    def contains(
        self,
        order_id: str,
    ) -> bool:
        """指定注文IDがキューにあるか返す。"""

        normalized = order_id.strip()

        if not normalized:
            raise ValueError(
                "注文IDを指定してください。"
            )

        return normalized in self._order_ids

    def snapshot(self) -> tuple[
        QueuedBacktestOrder,
        ...
    ]:
        """現在のキュー内容をFIFO順で返す。"""

        return tuple(self._items)

    def clear(self) -> None:
        """キューを空にする。"""

        self._items.clear()
        self._order_ids.clear()

    @property
    def count(self) -> int:
        """キュー内注文件数を返す。"""

        return len(self._items)

    @property
    def is_empty(self) -> bool:
        """キューが空か返す。"""

        return not self._items
