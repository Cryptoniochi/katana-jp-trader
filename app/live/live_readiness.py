"""Paper Readinessと分離したLive専用安全診断。"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.live.execution_mode import (
    ExecutionModeSettings,
    TradingExecutionMode,
)
from app.live.kabu_station_read_only import (
    KabuStationReadOnlySnapshot,
)


@dataclass(frozen=True, slots=True)
class LiveReadinessItem:
    key: str
    label: str
    passed: bool
    message: str


@dataclass(frozen=True, slots=True)
class LiveReadinessReport:
    generated_at: datetime
    read_only_ready: bool
    shadow_ready: bool
    live_order_ready: bool
    state: str
    items: tuple[LiveReadinessItem, ...]

    def to_payload(self) -> dict[str, object]:
        return {
            "generated_at": self.generated_at.isoformat(),
            "state": self.state,
            "read_only_ready": self.read_only_ready,
            "shadow_ready": self.shadow_ready,
            "live_order_ready": self.live_order_ready,
            "items": [asdict(item) for item in self.items],
        }


class LiveReadinessChecker:
    """実口座読取とLive注文ロックを診断する。"""

    def check(
        self,
        *,
        snapshot: KabuStationReadOnlySnapshot,
        execution_settings: ExecutionModeSettings,
        shadow_report_path: Path,
    ) -> LiveReadinessReport:
        items: list[LiveReadinessItem] = []
        lock_safe = (
            execution_settings.mode is not TradingExecutionMode.LIVE
            and not execution_settings.live_armed
            and execution_settings.live_confirmation is None
        )
        items.append(
            LiveReadinessItem(
                key="live_order_lock",
                label="Live order lock",
                passed=lock_safe,
                message=(
                    "Live注文は安全にLOCKEDです。"
                    if lock_safe
                    else "Live解除設定が検出されました。直ちに解除してください。"
                ),
            )
        )
        items.append(
            LiveReadinessItem(
                key="read_only_api",
                label="kabu Station read-only API",
                passed=snapshot.connected,
                message=(
                    "wallet/orders/positionsを読取専用で取得しました。"
                    if snapshot.connected
                    else "読取専用取得が完了していません。 "
                    + "; ".join(snapshot.errors)
                ),
            )
        )
        no_active_orders = snapshot.active_order_count == 0
        items.append(
            LiveReadinessItem(
                key="broker_active_orders",
                label="Broker active orders",
                passed=no_active_orders,
                message=(
                    "実口座に有効注文はありません。"
                    if no_active_orders
                    else "実口座に有効注文があります。 "
                    f"count={snapshot.active_order_count}"
                ),
            )
        )
        items.append(
            LiveReadinessItem(
                key="broker_positions",
                label="Broker positions inventory",
                passed=snapshot.connected,
                message=(
                    "実口座保有を取得しました。 "
                    f"count={snapshot.position_count}"
                    if snapshot.connected
                    else "実口座保有を確認できません。"
                ),
            )
        )

        shadow_ready, shadow_message = self._shadow_status(
            Path(shadow_report_path)
        )
        items.append(
            LiveReadinessItem(
                key="shadow_reconciliation",
                label="Shadow reconciliation",
                passed=shadow_ready,
                message=shadow_message,
            )
        )
        items.append(
            LiveReadinessItem(
                key="live_order_adapter",
                label="Live order adapter",
                passed=False,
                message=(
                    "Live注文Adapterは未導入です。sendorderは使用できません。"
                ),
            )
        )

        read_only_ready = lock_safe and snapshot.connected
        return LiveReadinessReport(
            generated_at=datetime.now(timezone.utc),
            read_only_ready=read_only_ready,
            shadow_ready=shadow_ready,
            live_order_ready=False,
            state=(
                "live_read_only_ready"
                if read_only_ready
                else "blocked"
            ),
            items=tuple(items),
        )

    @staticmethod
    def _shadow_status(path: Path) -> tuple[bool, str]:
        if not path.exists():
            return False, f"Shadow照合レポートがありません。 path={path}"
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError) as error:
            return False, f"Shadow照合レポートを読めません。 error={error}"
        consistent = bool(payload.get("consistent"))
        issue_count = int(payload.get("issue_count") or 0)
        ready = consistent and issue_count == 0
        return (
            ready,
            "Shadow照合は整合しています。"
            if ready
            else "Shadow照合に確認事項があります。 "
            f"consistent={consistent} issue_count={issue_count}",
        )


class LiveReadinessReportWriter:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def write(self, report: LiveReadinessReport) -> dict[str, object]:
        payload = report.to_payload()
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
