"""戦略別パフォーマンス分析のデータモデル。"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime

@dataclass(frozen=True, slots=True)
class StrategyClosedTrade:
    strategy_name: str
    code: str
    entry_execution_id: str
    exit_execution_id: str
    entry_at: datetime
    exit_at: datetime
    quantity: int
    entry_price: float
    exit_price: float
    entry_cost: float
    exit_cost: float
    realized_profit_loss: float

    @property
    def holding_minutes(self) -> float:
        return (self.exit_at - self.entry_at).total_seconds() / 60.0

@dataclass(frozen=True, slots=True)
class StrategyPerformance:
    strategy_name: str
    signal_count: int
    execution_count: int
    completed_trade_count: int
    win_count: int
    loss_count: int
    break_even_count: int
    gross_profit: float
    gross_loss: float
    net_profit_loss: float
    average_profit: float | None
    average_loss: float | None
    win_rate: float | None
    profit_factor: float | None
    average_holding_minutes: float | None
    maximum_drawdown: float

@dataclass(frozen=True, slots=True)
class StrategyAnalyticsReport:
    generated_at: datetime
    database_path: str
    performances: tuple[StrategyPerformance, ...]
    closed_trades: tuple[StrategyClosedTrade, ...]
