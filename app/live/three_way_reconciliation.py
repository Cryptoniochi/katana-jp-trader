"""Paper、Shadow、実口座在庫を変更せずに照合する。"""

from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


TOKYO = ZoneInfo("Asia/Tokyo")


@dataclass(frozen=True, slots=True)
class ReconciliationOrder:
    """照合に必要な注文の最小表現。"""

    order_id: str
    signal_id: str
    code: str
    side: str
    quantity: int


@dataclass(frozen=True, slots=True)
class OrderMismatch:
    order_id: str
    paper: ReconciliationOrder
    shadow: ReconciliationOrder


@dataclass(frozen=True, slots=True)
class ThreeWayReconciliationReport:
    generated_at: datetime
    trading_date: date
    state: str
    consistent: bool
    paper_order_count: int
    shadow_order_count: int
    matched_order_count: int
    paper_only_order_ids: tuple[str, ...]
    shadow_only_order_ids: tuple[str, ...]
    mismatches: tuple[OrderMismatch, ...]
    broker_snapshot_connected: bool
    broker_active_order_count: int
    broker_position_count: int
    broker_active_order_ids: tuple[str, ...]
    broker_position_codes: tuple[str, ...]
    live_order_ready: bool
    message: str

    @property
    def issue_count(self) -> int:
        return (
            len(self.paper_only_order_ids)
            + len(self.shadow_only_order_ids)
            + len(self.mismatches)
            + (0 if self.broker_snapshot_connected else 1)
            + self.broker_active_order_count
            + self.broker_position_count
        )

    def to_payload(self) -> dict[str, object]:
        payload = asdict(self)
        payload["generated_at"] = self.generated_at.isoformat()
        payload["trading_date"] = self.trading_date.isoformat()
        payload["issue_count"] = self.issue_count
        return payload


class PaperExecutionReader:
    """約定台帳を注文単位へ集約する。"""

    def __init__(self, database_path: Path) -> None:
        self.database_path = Path(database_path)

    def read(self, trading_date: date) -> tuple[ReconciliationOrder, ...]:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        try:
            rows = connection.execute(
                """
                SELECT order_id, signal_id, code, side, quantity, executed_at
                FROM trade_executions
                ORDER BY executed_at, id
                """
            ).fetchall()
        finally:
            connection.close()

        grouped: dict[str, ReconciliationOrder] = {}
        for row in rows:
            if _tokyo_date(row["executed_at"]) != trading_date:
                continue
            order_id = str(row["order_id"])
            candidate = ReconciliationOrder(
                order_id=order_id,
                signal_id=str(row["signal_id"]),
                code=str(row["code"]),
                side=str(row["side"]).lower(),
                quantity=int(row["quantity"]),
            )
            existing = grouped.get(order_id)
            if existing is None:
                grouped[order_id] = candidate
                continue
            if (
                existing.signal_id != candidate.signal_id
                or existing.code != candidate.code
                or existing.side != candidate.side
            ):
                raise ValueError(
                    "同一order_idの約定属性が一致しません。"
                    f" order_id={order_id}"
                )
            grouped[order_id] = ReconciliationOrder(
                order_id=order_id,
                signal_id=existing.signal_id,
                code=existing.code,
                side=existing.side,
                quantity=existing.quantity + candidate.quantity,
            )
        return tuple(grouped[key] for key in sorted(grouped))


class ShadowLedgerReader:
    """Shadow台帳のsubmittedイベントを読む。"""

    def __init__(self, ledger_path: Path) -> None:
        self.ledger_path = Path(ledger_path)

    def read(self, trading_date: date) -> tuple[ReconciliationOrder, ...]:
        if not self.ledger_path.exists():
            return ()
        orders: dict[str, ReconciliationOrder] = {}
        for line_number, line in enumerate(
            self.ledger_path.read_text(encoding="utf-8").splitlines(),
            start=1,
        ):
            if not line.strip():
                continue
            event = json.loads(line)
            if event.get("event") != "submitted":
                continue
            if _tokyo_date(event["recorded_at"]) != trading_date:
                continue
            order = event.get("order")
            if not isinstance(order, dict):
                raise ValueError(
                    f"Shadow注文が不正です。 line={line_number}"
                )
            candidate = ReconciliationOrder(
                order_id=str(order["order_id"]),
                signal_id=str(order["signal_id"]),
                code=str(order["code"]),
                side=str(order["side"]).lower(),
                quantity=int(order["quantity"]),
            )
            if candidate.order_id in orders:
                raise ValueError(
                    "Shadow台帳にorder_idの重複があります。"
                    f" order_id={candidate.order_id}"
                )
            orders[candidate.order_id] = candidate
        return tuple(orders[key] for key in sorted(orders))


class BrokerInventoryReader:
    """Phase 5-AのGET専用Snapshotから実口座在庫を読む。"""

    def __init__(self, report_path: Path) -> None:
        self.report_path = Path(report_path)

    def read(self) -> tuple[bool, tuple[str, ...], tuple[str, ...]]:
        payload = json.loads(self.report_path.read_text(encoding="utf-8"))
        connected = bool(payload.get("connected"))
        orders = payload.get("orders") or []
        positions = payload.get("positions") or []
        active_order_ids = tuple(
            sorted(
                str(item.get("ID") or item.get("OrderId") or "unknown")
                for item in orders
                if isinstance(item, dict)
                and int(item.get("State") or 0) in {1, 2, 3, 4}
            )
        )
        position_codes = tuple(
            sorted(
                str(item.get("Symbol") or item.get("Code") or "unknown")
                for item in positions
                if isinstance(item, dict)
            )
        )
        return connected, active_order_ids, position_codes


class ThreeWayReconciliationService:
    """Paper↔Shadowの一致と実口座が空であることを確認する。"""

    def reconcile(
        self,
        *,
        trading_date: date,
        paper_orders: tuple[ReconciliationOrder, ...],
        shadow_orders: tuple[ReconciliationOrder, ...],
        broker_snapshot_connected: bool,
        broker_active_order_ids: tuple[str, ...],
        broker_position_codes: tuple[str, ...],
    ) -> ThreeWayReconciliationReport:
        paper = {item.order_id: item for item in paper_orders}
        shadow = {item.order_id: item for item in shadow_orders}
        paper_ids = set(paper)
        shadow_ids = set(shadow)
        shared_ids = paper_ids & shadow_ids
        mismatches = tuple(
            OrderMismatch(order_id, paper[order_id], shadow[order_id])
            for order_id in sorted(shared_ids)
            if paper[order_id] != shadow[order_id]
        )
        matched_count = len(shared_ids) - len(mismatches)
        paper_only = tuple(sorted(paper_ids - shadow_ids))
        shadow_only = tuple(sorted(shadow_ids - paper_ids))
        consistent = (
            broker_snapshot_connected
            and not paper_only
            and not shadow_only
            and not mismatches
            and not broker_active_order_ids
            and not broker_position_codes
        )
        return ThreeWayReconciliationReport(
            generated_at=datetime.now(timezone.utc),
            trading_date=trading_date,
            state="consistent" if consistent else "blocked",
            consistent=consistent,
            paper_order_count=len(paper),
            shadow_order_count=len(shadow),
            matched_order_count=matched_count,
            paper_only_order_ids=paper_only,
            shadow_only_order_ids=shadow_only,
            mismatches=mismatches,
            broker_snapshot_connected=broker_snapshot_connected,
            broker_active_order_count=len(broker_active_order_ids),
            broker_position_count=len(broker_position_codes),
            broker_active_order_ids=broker_active_order_ids,
            broker_position_codes=broker_position_codes,
            live_order_ready=False,
            message=(
                "Paper/Shadowは一致し、実口座に有効注文・保有は"
                "ありません。"
                if consistent
                else "三者照合に確認事項があります。"
                "Live注文はBLOCKEDです。"
            ),
        )


class ThreeWayReconciliationReportWriter:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def write(self, report: ThreeWayReconciliationReport) -> dict[str, object]:
        payload = report.to_payload()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.{os.getpid()}.tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, self.path)
        return payload


def _tokyo_date(value: object) -> date:
    timestamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(TOKYO).date()
