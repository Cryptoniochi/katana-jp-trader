"""SQLiteから戦略別Dashboardサマリーを生成する。"""

from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class DashboardStrategyRow:
    """Dashboardへ表示する1戦略の集計。"""

    strategy_name: str
    signal_count: int
    execution_count: int
    completed_trade_count: int
    win_count: int
    loss_count: int
    net_profit_loss: float
    win_rate: float | None
    profit_factor: float | None
    candidate_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class DashboardRecentTrade:
    """Dashboardへ表示する最近の約定。"""

    executed_at: datetime
    strategy_name: str
    code: str
    side: str
    quantity: int
    execution_price: float
    commission: float
    slippage: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "executed_at": self.executed_at.isoformat(),
            "strategy_name": self.strategy_name,
            "code": self.code,
            "side": self.side,
            "quantity": self.quantity,
            "execution_price": self.execution_price,
            "commission": self.commission,
            "slippage": self.slippage,
        }


@dataclass(frozen=True, slots=True)
class DashboardStrategyPayload:
    """戦略Dashboard APIのPayload。"""

    generated_at: datetime
    trading_date: date
    strategies: tuple[DashboardStrategyRow, ...]
    recent_trades: tuple[DashboardRecentTrade, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at.isoformat(),
            "trading_date": self.trading_date.isoformat(),
            "strategies": [
                item.to_dict()
                for item in self.strategies
            ],
            "recent_trades": [
                item.to_dict()
                for item in self.recent_trades
            ],
        }


class DashboardStrategyService:
    """戦略別のシグナル・約定・損益をSQLiteから集約する。"""

    DISPLAY_STRATEGIES = (
        "opening-range-breakout-v2",
        "pullback-breakout-v1",
        "high-breakout-v1",
    )

    DISPLAY_NAMES = {
        "opening-range-breakout-v2": "ORB",
        "pullback-breakout-v1": "Pullback",
        "high-breakout-v1": "High Breakout",
    }

    def __init__(
        self,
        database_path: Path,
        *,
        recent_trade_limit: int = 20,
        now_provider=None,
    ) -> None:
        if recent_trade_limit <= 0:
            raise ValueError(
                "最近約定件数は0より大きい必要があります。"
            )

        self.database_path = Path(database_path)
        self.recent_trade_limit = recent_trade_limit
        self.now_provider = (
            now_provider
            if now_provider is not None
            else lambda: datetime.now(timezone.utc)
        )

    def create_payload(
        self,
        *,
        trading_date: date | None = None,
    ) -> DashboardStrategyPayload:
        """指定営業日の戦略サマリーを生成する。"""

        generated_at = self._current_time()
        target_date = (
            trading_date
            if trading_date is not None
            else generated_at.astimezone().date()
        )

        if not self.database_path.exists():
            return DashboardStrategyPayload(
                generated_at=generated_at,
                trading_date=target_date,
                strategies=self._empty_rows(),
                recent_trades=(),
            )

        with sqlite3.connect(
            self.database_path
        ) as connection:
            signal_counts = self._load_signal_counts(
                connection,
                target_date,
            )
            execution_counts = self._load_execution_counts(
                connection,
                target_date,
            )
            candidate_count = self._load_candidate_count(
                connection,
                target_date,
            )
            closed_stats = self._load_closed_trade_stats(
                connection,
                target_date,
            )
            recent_trades = self._load_recent_trades(
                connection,
            )

        rows = []

        for strategy_name in self.DISPLAY_STRATEGIES:
            stats = closed_stats.get(
                strategy_name,
                {
                    "completed_trade_count": 0,
                    "win_count": 0,
                    "loss_count": 0,
                    "net_profit_loss": 0.0,
                    "gross_profit": 0.0,
                    "gross_loss": 0.0,
                },
            )
            trade_count = int(
                stats["completed_trade_count"]
            )
            win_count = int(stats["win_count"])
            gross_profit = float(
                stats["gross_profit"]
            )
            gross_loss = float(
                stats["gross_loss"]
            )

            rows.append(
                DashboardStrategyRow(
                    strategy_name=self.DISPLAY_NAMES[
                        strategy_name
                    ],
                    signal_count=signal_counts.get(
                        strategy_name,
                        0,
                    ),
                    execution_count=execution_counts.get(
                        strategy_name,
                        0,
                    ),
                    completed_trade_count=trade_count,
                    win_count=win_count,
                    loss_count=int(stats["loss_count"]),
                    net_profit_loss=float(
                        stats["net_profit_loss"]
                    ),
                    win_rate=(
                        win_count / trade_count
                        if trade_count > 0
                        else None
                    ),
                    profit_factor=(
                        gross_profit / abs(gross_loss)
                        if gross_loss < 0
                        else (
                            float("inf")
                            if gross_profit > 0
                            else None
                        )
                    ),
                    candidate_count=(
                        candidate_count
                        if strategy_name
                        == "high-breakout-v1"
                        else 0
                    ),
                )
            )

        return DashboardStrategyPayload(
            generated_at=generated_at,
            trading_date=target_date,
            strategies=tuple(rows),
            recent_trades=recent_trades,
        )

    @classmethod
    def _empty_rows(
        cls,
    ) -> tuple[DashboardStrategyRow, ...]:
        return tuple(
            DashboardStrategyRow(
                strategy_name=cls.DISPLAY_NAMES[name],
                signal_count=0,
                execution_count=0,
                completed_trade_count=0,
                win_count=0,
                loss_count=0,
                net_profit_loss=0.0,
                win_rate=None,
                profit_factor=None,
                candidate_count=0,
            )
            for name in cls.DISPLAY_STRATEGIES
        )

    @staticmethod
    def _table_exists(
        connection: sqlite3.Connection,
        table_name: str,
    ) -> bool:
        row = connection.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type = 'table'
              AND name = ?
            """,
            (table_name,),
        ).fetchone()
        return row is not None

    @classmethod
    def _load_signal_counts(
        cls,
        connection: sqlite3.Connection,
        trading_date: date,
    ) -> dict[str, int]:
        if not cls._table_exists(
            connection,
            "trade_signals",
        ):
            return {}

        rows = connection.execute(
            """
            SELECT strategy_name, COUNT(*)
            FROM trade_signals
            WHERE substr(generated_at, 1, 10) = ?
            GROUP BY strategy_name
            """,
            (trading_date.isoformat(),),
        ).fetchall()

        return {
            str(name): int(count)
            for name, count in rows
        }

    @classmethod
    def _load_execution_counts(
        cls,
        connection: sqlite3.Connection,
        trading_date: date,
    ) -> dict[str, int]:
        if not (
            cls._table_exists(
                connection,
                "trade_executions",
            )
            and cls._table_exists(
                connection,
                "trade_signals",
            )
        ):
            return {}

        rows = connection.execute(
            """
            SELECT s.strategy_name, COUNT(*)
            FROM trade_executions AS e
            JOIN trade_signals AS s
              ON s.signal_id = e.signal_id
            WHERE substr(e.executed_at, 1, 10) = ?
            GROUP BY s.strategy_name
            """,
            (trading_date.isoformat(),),
        ).fetchall()

        return {
            str(name): int(count)
            for name, count in rows
        }

    @classmethod
    def _load_candidate_count(
        cls,
        connection: sqlite3.Connection,
        trading_date: date,
    ) -> int:
        if not cls._table_exists(
            connection,
            "high_breakout_candidates",
        ):
            return 0

        row = connection.execute(
            """
            SELECT COUNT(*)
            FROM high_breakout_candidates
            WHERE trading_date = ?
            """,
            (trading_date.isoformat(),),
        ).fetchone()

        return int(row[0]) if row is not None else 0

    @classmethod
    def _load_closed_trade_stats(
        cls,
        connection: sqlite3.Connection,
        trading_date: date,
    ) -> dict[str, dict[str, float | int]]:
        if not (
            cls._table_exists(
                connection,
                "trade_executions",
            )
            and cls._table_exists(
                connection,
                "trade_signals",
            )
        ):
            return {}

        rows = connection.execute(
            """
            SELECT
                e.execution_id,
                e.code,
                e.side,
                e.quantity,
                e.execution_price,
                e.executed_at,
                e.commission,
                e.slippage,
                s.strategy_name,
                s.action
            FROM trade_executions AS e
            JOIN trade_signals AS s
              ON s.signal_id = e.signal_id
            WHERE substr(e.executed_at, 1, 10) = ?
            ORDER BY e.executed_at ASC, e.id ASC
            """,
            (trading_date.isoformat(),),
        ).fetchall()

        open_entries: dict[
            tuple[str, str],
            list[dict[str, float | int]],
        ] = {}
        pnl_by_strategy: dict[str, list[float]] = {}

        for row in rows:
            code = str(row[1])
            side = str(row[2]).lower()
            quantity = int(row[3])
            price = float(row[4])
            commission = float(row[6])
            slippage = float(row[7])
            strategy_name = str(row[8])
            action = str(row[9]).lower()
            key = (
                strategy_name,
                code,
            )

            if action == "buy" or side == "buy":
                open_entries.setdefault(
                    key,
                    [],
                ).append(
                    {
                        "quantity": quantity,
                        "remaining": quantity,
                        "price": price,
                        "cost": commission + slippage,
                    }
                )
                continue

            if (
                action not in {"sell", "exit"}
                and side != "sell"
            ):
                continue

            remaining_exit = quantity
            entries = open_entries.setdefault(
                key,
                [],
            )

            while remaining_exit > 0 and entries:
                entry = entries[0]
                matched = min(
                    int(entry["remaining"]),
                    remaining_exit,
                )
                entry_cost = (
                    float(entry["cost"])
                    * matched
                    / int(entry["quantity"])
                )
                exit_cost = (
                    (commission + slippage)
                    * matched
                    / quantity
                )
                pnl = (
                    (
                        price
                        - float(entry["price"])
                    )
                    * matched
                    - entry_cost
                    - exit_cost
                )
                pnl_by_strategy.setdefault(
                    strategy_name,
                    [],
                ).append(pnl)

                entry["remaining"] = (
                    int(entry["remaining"])
                    - matched
                )
                remaining_exit -= matched

                if int(entry["remaining"]) == 0:
                    entries.pop(0)

        result = {}

        for strategy_name, values in pnl_by_strategy.items():
            profits = [
                value
                for value in values
                if value > 0
            ]
            losses = [
                value
                for value in values
                if value < 0
            ]
            result[strategy_name] = {
                "completed_trade_count": len(values),
                "win_count": len(profits),
                "loss_count": len(losses),
                "net_profit_loss": sum(values),
                "gross_profit": sum(profits),
                "gross_loss": sum(losses),
            }

        return result

    def _load_recent_trades(
        self,
        connection: sqlite3.Connection,
    ) -> tuple[DashboardRecentTrade, ...]:
        if not (
            self._table_exists(
                connection,
                "trade_executions",
            )
            and self._table_exists(
                connection,
                "trade_signals",
            )
        ):
            return ()

        rows = connection.execute(
            """
            SELECT
                e.executed_at,
                s.strategy_name,
                e.code,
                e.side,
                e.quantity,
                e.execution_price,
                e.commission,
                e.slippage
            FROM trade_executions AS e
            JOIN trade_signals AS s
              ON s.signal_id = e.signal_id
            ORDER BY e.executed_at DESC, e.id DESC
            LIMIT ?
            """,
            (self.recent_trade_limit,),
        ).fetchall()

        return tuple(
            DashboardRecentTrade(
                executed_at=self._parse_datetime(
                    str(row[0])
                ),
                strategy_name=self.DISPLAY_NAMES.get(
                    str(row[1]),
                    str(row[1]),
                ),
                code=str(row[2]),
                side=str(row[3]).upper(),
                quantity=int(row[4]),
                execution_price=float(row[5]),
                commission=float(row[6]),
                slippage=float(row[7]),
            )
            for row in rows
        )

    def _current_time(self) -> datetime:
        value = self.now_provider()

        if value.tzinfo is None:
            raise ValueError(
                "現在日時にはタイムゾーンが必要です。"
            )

        return value.astimezone(timezone.utc)

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
