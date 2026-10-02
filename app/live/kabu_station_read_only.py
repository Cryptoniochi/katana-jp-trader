"""kabuステーション実口座を変更せずに照会する。"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from app.market.kabu_station_client import KabuStationClient


@dataclass(frozen=True, slots=True)
class KabuStationReadOnlySnapshot:
    """実口座GET APIの取得結果。"""

    generated_at: datetime
    state: str
    connected: bool
    token_issued: bool
    cash_wallet: dict[str, object] | None
    margin_wallet: dict[str, object] | None
    positions: tuple[dict[str, object], ...]
    orders: tuple[dict[str, object], ...]
    errors: tuple[str, ...]

    @property
    def position_count(self) -> int:
        return len(self.positions)

    @property
    def order_count(self) -> int:
        return len(self.orders)

    @property
    def active_order_count(self) -> int:
        return sum(
            int(order.get("State") or 0) in {1, 2, 3, 4}
            for order in self.orders
        )

    def to_payload(self) -> dict[str, object]:
        payload = asdict(self)
        payload["generated_at"] = self.generated_at.isoformat()
        payload["position_count"] = self.position_count
        payload["order_count"] = self.order_count
        payload["active_order_count"] = self.active_order_count
        return payload


class KabuStationReadOnlyService:
    """トークンとGET系だけを利用して実口座を取得する。"""

    def __init__(
        self,
        *,
        client: KabuStationClient,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self.client = client
        self.now_provider = now_provider or (
            lambda: datetime.now(timezone.utc)
        )

    def collect(self) -> KabuStationReadOnlySnapshot:
        """4種類の読取専用Endpointを独立に取得する。"""

        generated_at = self._now()
        try:
            self.client.issue_token()
        except Exception as error:
            return KabuStationReadOnlySnapshot(
                generated_at=generated_at,
                state="failed",
                connected=False,
                token_issued=False,
                cash_wallet=None,
                margin_wallet=None,
                positions=(),
                orders=(),
                errors=(self._error("token", error),),
            )

        errors: list[str] = []
        cash_wallet = self._capture(
            "wallet/cash", self.client.cash_wallet, errors
        )
        margin_wallet = self._capture(
            "wallet/margin", self.client.margin_wallet, errors
        )
        positions = self._capture(
            "positions", self.client.positions, errors
        )
        orders = self._capture("orders", self.client.orders, errors)

        state = "complete" if not errors else "partial"
        return KabuStationReadOnlySnapshot(
            generated_at=generated_at,
            state=state,
            connected=not errors,
            token_issued=True,
            cash_wallet=(
                cash_wallet if isinstance(cash_wallet, dict) else None
            ),
            margin_wallet=(
                margin_wallet if isinstance(margin_wallet, dict) else None
            ),
            positions=tuple(positions or ()),
            orders=tuple(orders or ()),
            errors=tuple(errors),
        )

    @staticmethod
    def _capture(name, operation, errors):
        try:
            return operation()
        except Exception as error:
            errors.append(KabuStationReadOnlyService._error(name, error))
            return None

    @staticmethod
    def _error(name: str, error: Exception) -> str:
        message = str(error).strip() or type(error).__name__
        return f"{name}: {message}"

    def _now(self) -> datetime:
        current = self.now_provider()
        if current.tzinfo is None:
            return current.replace(tzinfo=timezone.utc)
        return current.astimezone(timezone.utc)


class KabuStationReadOnlyReportWriter:
    """読取専用Snapshotを原子的に保存する。"""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def write(
        self,
        snapshot: KabuStationReadOnlySnapshot,
    ) -> dict[str, object]:
        payload = snapshot.to_payload()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(
            f".{self.path.name}.{os.getpid()}.tmp"
        )
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, self.path)
        return payload
