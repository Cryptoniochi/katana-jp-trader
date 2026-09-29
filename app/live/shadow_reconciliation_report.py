"""Paper注文とShadow注文計画の日次照合レポート。"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from datetime import date, datetime, timezone
from pathlib import Path
from threading import RLock
from zoneinfo import ZoneInfo

from app.live.paper_shadow_replication import (
    PaperShadowReplicationBatchResult,
)


TOKYO = ZoneInfo("Asia/Tokyo")


class ShadowReconciliationReportWriter:
    """Shadow複製結果を注文ID単位で冪等に日次集計する。"""

    def __init__(
        self,
        *,
        report_path: Path,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self.report_path = Path(report_path)
        self.now_provider = (
            now_provider
            if now_provider is not None
            else lambda: datetime.now(timezone.utc)
        )
        self._lock = RLock()

    def initialize(self) -> dict[str, object]:
        """有効化済み・注文待ちのレポートを作成する。"""

        with self._lock:
            current_time = self._current_time()
            payload = self._load_for_date(
                current_time.astimezone(TOKYO).date()
            )
            return self._write(payload, current_time)

    def record(
        self,
        result: PaperShadowReplicationBatchResult,
    ) -> dict[str, object]:
        """1バッチの結果を日次レポートへ反映する。"""

        with self._lock:
            current_time = self._current_time()
            trading_date = current_time.astimezone(TOKYO).date()
            payload = self._load_for_date(trading_date)
            orders = {
                str(item.get("order_id", "")): item
                for item in payload.get("orders", [])
                if str(item.get("order_id", ""))
            }

            for item in result.items:
                order = item.paper_order
                shadow = item.shadow_result
                previous = orders.get(order.order_id)
                decision = item.decision.value

                if (
                    previous is not None
                    and previous.get("decision") == "recorded"
                    and decision == "existing"
                ):
                    decision = "recorded"

                orders[order.order_id] = {
                    "order_id": order.order_id,
                    "signal_id": order.signal_id,
                    "code": order.code,
                    "side": order.side.value,
                    "order_type": order.order_type.value,
                    "quantity": order.quantity,
                    "limit_price": order.limit_price,
                    "stop_price": order.stop_price,
                    "decision": decision,
                    "message": item.message,
                    "shadow_broker_order_id": (
                        shadow.snapshot.broker_order_id
                        if shadow is not None
                        else None
                    ),
                    "idempotency_key": (
                        shadow.idempotency_key
                        if shadow is not None
                        else None
                    ),
                }

            payload["orders"] = list(orders.values())
            payload["initialization_error"] = None
            return self._write(payload, current_time)

    def record_initialization_error(
        self,
        error: Exception,
    ) -> dict[str, object]:
        """Shadow初期化失敗をPaper運転と分離して記録する。"""

        with self._lock:
            current_time = self._current_time()
            payload = self._load_for_date(
                current_time.astimezone(TOKYO).date()
            )
            payload["initialization_error"] = (
                str(error).strip() or type(error).__name__
            )
            return self._write(payload, current_time)

    def _load_for_date(
        self,
        trading_date: date,
    ) -> dict[str, object]:
        expected = trading_date.isoformat()

        if self.report_path.exists():
            try:
                payload = json.loads(
                    self.report_path.read_text(encoding="utf-8")
                )
                if payload.get("trading_date") == expected:
                    return payload
            except (OSError, ValueError, TypeError):
                pass

        return {
            "generated_at": None,
            "trading_date": expected,
            "state": "waiting",
            "enabled": True,
            "consistent": True,
            "input_count": 0,
            "replicated_count": 0,
            "recorded_count": 0,
            "existing_count": 0,
            "skipped_count": 0,
            "failed_count": 0,
            "mismatch_count": 0,
            "initialization_error": None,
            "orders": [],
        }

    def _write(
        self,
        payload: dict[str, object],
        current_time: datetime,
    ) -> dict[str, object]:
        orders = list(payload.get("orders", []))
        counts = {
            decision: sum(
                item.get("decision") == decision
                for item in orders
            )
            for decision in (
                "recorded",
                "existing",
                "skipped",
                "failed",
                "mismatch",
            )
        }
        failed_count = counts["failed"]
        mismatch_count = counts["mismatch"]
        initialization_error = payload.get(
            "initialization_error"
        )
        consistent = (
            failed_count == 0
            and mismatch_count == 0
            and initialization_error is None
        )

        payload.update(
            {
                "generated_at": current_time.isoformat(),
                "state": (
                    "consistent"
                    if orders and consistent
                    else "attention"
                    if orders or initialization_error is not None
                    else "waiting"
                ),
                "enabled": True,
                "consistent": consistent,
                "input_count": len(orders),
                "replicated_count": (
                    counts["recorded"] + counts["existing"]
                ),
                "recorded_count": counts["recorded"],
                "existing_count": counts["existing"],
                "skipped_count": counts["skipped"],
                "failed_count": failed_count,
                "mismatch_count": mismatch_count,
                "issue_count": (
                    failed_count
                    + mismatch_count
                    + int(initialization_error is not None)
                ),
                "initialization_error": initialization_error,
                "orders": orders,
            }
        )

        self.report_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.report_path.with_name(
            f".{self.report_path.name}.{os.getpid()}.tmp"
        )
        temporary_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary_path, self.report_path)
        return payload

    def _current_time(self) -> datetime:
        current = self.now_provider()

        if current.tzinfo is None:
            return current.replace(tzinfo=timezone.utc)

        return current
