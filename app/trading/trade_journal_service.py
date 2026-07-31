"""約定履歴からTrade Journalを再構築する。"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path

from app.trading.trade_journal_models import (
    TradeJournalEntry,
)
from app.trading.trade_journal_repository import (
    TradeJournalRepository,
)


class TradeJournalBuildError(RuntimeError):
    """Trade Journal生成処理の例外。"""


class TradeJournalService:
    """保存済み約定をFIFO対応し、完了トレードを作る。"""

    def __init__(
        self,
        database_path: Path,
        *,
        market_bar_interval_minutes: int = 5,
    ) -> None:
        if market_bar_interval_minutes <= 0:
            raise ValueError(
                "市場データ時間足は0より大きい必要があります。"
            )

        self.database_path = Path(database_path)
        self.market_bar_interval_minutes = (
            market_bar_interval_minutes
        )
        self.repository = TradeJournalRepository(
            self.database_path
        )

    def rebuild(self) -> tuple[TradeJournalEntry, ...]:
        """約定履歴から全完了トレードを再構築して保存する。"""

        if not self.database_path.exists():
            raise TradeJournalBuildError(
                "データベースが存在しません。 "
                f"path={self.database_path}"
            )

        try:
            with sqlite3.connect(
                self.database_path
            ) as connection:
                executions = self._load_executions(
                    connection
                )
                entries = self._match_executions(
                    connection,
                    executions,
                )
        except sqlite3.Error as error:
            raise TradeJournalBuildError(
                "Trade Journal生成用データを"
                "読み込めませんでした。"
            ) from error

        self.repository.save_all(entries)
        return entries

    @staticmethod
    def _load_executions(
        connection: sqlite3.Connection,
    ) -> tuple[dict[str, object], ...]:
        rows = connection.execute(
            """
            SELECT
                e.id,
                e.execution_id,
                e.signal_id,
                e.code,
                e.side,
                e.quantity,
                e.execution_price,
                e.executed_at,
                e.commission,
                e.slippage,
                s.strategy_name,
                s.action,
                s.reason,
                s.metadata_json
            FROM trade_executions AS e
            JOIN trade_signals AS s
              ON s.signal_id = e.signal_id
            ORDER BY e.executed_at ASC, e.id ASC
            """
        ).fetchall()

        result = []

        for row in rows:
            try:
                signal_metadata = json.loads(
                    str(row[13] or "{}")
                )
            except (
                TypeError,
                ValueError,
                json.JSONDecodeError,
            ):
                signal_metadata = {}

            result.append(
                {
                    "row_id": int(row[0]),
                    "execution_id": str(row[1]),
                    "signal_id": str(row[2]),
                    "code": str(row[3]),
                    "side": str(row[4]).lower(),
                    "quantity": int(row[5]),
                    "execution_price": float(row[6]),
                    "executed_at": (
                        TradeJournalService._parse_datetime(
                            str(row[7])
                        )
                    ),
                    "commission": float(row[8]),
                    "slippage": float(row[9]),
                    "strategy_name": str(row[10]),
                    "action": str(row[11]).lower(),
                    "signal_reason": str(row[12]),
                    "signal_metadata": signal_metadata,
                }
            )

        return tuple(result)

    def _match_executions(
        self,
        connection: sqlite3.Connection,
        executions: tuple[dict[str, object], ...],
    ) -> tuple[TradeJournalEntry, ...]:
        open_entries: dict[
            tuple[str, str],
            deque[dict[str, object]],
        ] = defaultdict(deque)
        completed: list[TradeJournalEntry] = []
        pair_sequence: dict[
            tuple[str, str],
            int,
        ] = defaultdict(int)

        for execution in executions:
            key = (
                str(execution["strategy_name"]),
                str(execution["code"]),
            )
            action = str(execution["action"])
            side = str(execution["side"])

            if action == "buy" or side == "buy":
                open_entries[key].append(
                    {
                        **execution,
                        "remaining": int(
                            execution["quantity"]
                        ),
                    }
                )
                continue

            if (
                action not in {"sell", "exit"}
                and side != "sell"
            ):
                continue

            exit_remaining = int(
                execution["quantity"]
            )
            exit_total = int(
                execution["quantity"]
            )

            while (
                exit_remaining > 0
                and open_entries[key]
            ):
                entry = open_entries[key][0]
                entry_remaining = int(
                    entry["remaining"]
                )
                matched_quantity = min(
                    entry_remaining,
                    exit_remaining,
                )

                entry_cost = (
                    float(entry["commission"])
                    + float(entry["slippage"])
                ) * matched_quantity / int(
                    entry["quantity"]
                )
                exit_cost = (
                    float(execution["commission"])
                    + float(execution["slippage"])
                ) * matched_quantity / exit_total

                entry_price = float(
                    entry["execution_price"]
                )
                exit_price = float(
                    execution["execution_price"]
                )
                gross_profit_loss = (
                    exit_price - entry_price
                ) * matched_quantity
                realized_profit_loss = (
                    gross_profit_loss
                    - entry_cost
                    - exit_cost
                )
                acquisition_value = (
                    entry_price * matched_quantity
                )
                return_rate = (
                    realized_profit_loss
                    / acquisition_value
                )

                entry_at = entry["executed_at"]
                exit_at = execution["executed_at"]
                excursions = self._calculate_excursions(
                    connection,
                    code=str(execution["code"]),
                    entry_at=entry_at,
                    exit_at=exit_at,
                    entry_price=entry_price,
                    quantity=matched_quantity,
                )

                pair_key = (
                    str(entry["execution_id"]),
                    str(execution["execution_id"]),
                )
                pair_sequence[pair_key] += 1
                trade_id = self._trade_id(
                    entry_execution_id=pair_key[0],
                    exit_execution_id=pair_key[1],
                    sequence=pair_sequence[pair_key],
                )

                completed.append(
                    TradeJournalEntry(
                        trade_id=trade_id,
                        strategy_name=str(
                            execution["strategy_name"]
                        ),
                        code=str(execution["code"]),
                        entry_signal_id=str(
                            entry["signal_id"]
                        ),
                        exit_signal_id=str(
                            execution["signal_id"]
                        ),
                        entry_execution_id=str(
                            entry["execution_id"]
                        ),
                        exit_execution_id=str(
                            execution["execution_id"]
                        ),
                        entry_at=entry_at,
                        exit_at=exit_at,
                        entry_price=entry_price,
                        exit_price=exit_price,
                        quantity=matched_quantity,
                        entry_cost=entry_cost,
                        exit_cost=exit_cost,
                        realized_profit_loss=(
                            realized_profit_loss
                        ),
                        return_rate=return_rate,
                        holding_minutes=(
                            exit_at - entry_at
                        ).total_seconds() / 60.0,
                        exit_reason=self._exit_reason(
                            execution
                        ),
                        maximum_favorable_excursion=(
                            excursions["mfe"]
                        ),
                        maximum_adverse_excursion=(
                            excursions["mae"]
                        ),
                        maximum_favorable_excursion_rate=(
                            excursions["mfe_rate"]
                        ),
                        maximum_adverse_excursion_rate=(
                            excursions["mae_rate"]
                        ),
                        metadata={
                            "gross_profit_loss": (
                                gross_profit_loss
                            ),
                            "entry_signal_reason": (
                                entry["signal_reason"]
                            ),
                            "exit_signal_reason": (
                                execution["signal_reason"]
                            ),
                            "market_bar_interval_minutes": (
                                self.market_bar_interval_minutes
                            ),
                        },
                    )
                )

                entry["remaining"] = (
                    entry_remaining
                    - matched_quantity
                )
                exit_remaining -= matched_quantity

                if int(entry["remaining"]) == 0:
                    open_entries[key].popleft()

        return tuple(completed)

    def _calculate_excursions(
        self,
        connection: sqlite3.Connection,
        *,
        code: str,
        entry_at: datetime,
        exit_at: datetime,
        entry_price: float,
        quantity: int,
    ) -> dict[str, float | None]:
        rows = connection.execute(
            """
            SELECT high, low
            FROM market_bars
            WHERE code = ?
              AND interval_minutes = ?
              AND traded_at >= ?
              AND traded_at <= ?
            ORDER BY traded_at ASC
            """,
            (
                code,
                self.market_bar_interval_minutes,
                entry_at.isoformat(),
                exit_at.isoformat(),
            ),
        ).fetchall()

        if not rows:
            return {
                "mfe": None,
                "mae": None,
                "mfe_rate": None,
                "mae_rate": None,
            }

        maximum_high = max(
            float(row[0])
            for row in rows
        )
        minimum_low = min(
            float(row[1])
            for row in rows
        )
        mfe_per_share = max(
            0.0,
            maximum_high - entry_price,
        )
        mae_per_share = min(
            0.0,
            minimum_low - entry_price,
        )

        return {
            "mfe": mfe_per_share * quantity,
            "mae": mae_per_share * quantity,
            "mfe_rate": (
                mfe_per_share / entry_price
            ),
            "mae_rate": (
                mae_per_share / entry_price
            ),
        }

    @staticmethod
    def _exit_reason(
        execution: dict[str, object],
    ) -> str | None:
        metadata = execution["signal_metadata"]

        if isinstance(metadata, dict):
            value = metadata.get("exit_reason")

            if value is not None and str(value).strip():
                return str(value).strip()

        reason = str(
            execution["signal_reason"]
        ).strip()
        return reason or None

    @staticmethod
    def _trade_id(
        *,
        entry_execution_id: str,
        exit_execution_id: str,
        sequence: int,
    ) -> str:
        digest = hashlib.sha256(
            (
                f"{entry_execution_id}|"
                f"{exit_execution_id}|"
                f"{sequence}"
            ).encode("utf-8")
        ).hexdigest()[:20]
        return f"journal-{digest}"

    @staticmethod
    def _parse_datetime(
        value: str,
    ) -> datetime:
        parsed = datetime.fromisoformat(value)

        if parsed.tzinfo is None:
            parsed = parsed.replace(
                tzinfo=timezone.utc
            )

        return parsed.astimezone(timezone.utc)
