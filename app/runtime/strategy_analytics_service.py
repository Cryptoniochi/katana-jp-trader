"""SQLiteのシグナル・約定から戦略別成績を集計する。"""
from __future__ import annotations
import sqlite3
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from app.runtime.strategy_analytics_models import StrategyAnalyticsReport, StrategyClosedTrade, StrategyPerformance

class StrategyAnalyticsError(RuntimeError):
    pass

class StrategyAnalyticsService:
    def __init__(self, database_path: Path, *, now_provider=None) -> None:
        self.database_path = Path(database_path)
        self.now_provider = now_provider or (lambda: datetime.now(timezone.utc))

    def analyze(self) -> StrategyAnalyticsReport:
        if not self.database_path.exists():
            raise StrategyAnalyticsError(f"分析対象DBが存在しません。 path={self.database_path}")
        with sqlite3.connect(self.database_path) as connection:
            signal_counts = dict(connection.execute("SELECT strategy_name, COUNT(*) FROM trade_signals GROUP BY strategy_name").fetchall())
            execution_counts = dict(connection.execute("SELECT s.strategy_name, COUNT(*) FROM trade_executions e JOIN trade_signals s ON s.signal_id=e.signal_id GROUP BY s.strategy_name").fetchall())
            rows = connection.execute("""
                SELECT e.execution_id,e.code,e.side,e.quantity,e.execution_price,e.executed_at,
                       e.commission,e.slippage,s.strategy_name,s.action
                FROM trade_executions e JOIN trade_signals s ON s.signal_id=e.signal_id
                ORDER BY e.executed_at ASC,e.id ASC
            """).fetchall()
        executions = [dict(execution_id=str(r[0]), code=str(r[1]), side=str(r[2]).lower(), quantity=int(r[3]), execution_price=float(r[4]), executed_at=self._dt(str(r[5])), commission=float(r[6]), slippage=float(r[7]), strategy_name=str(r[8]), action=str(r[9]).lower()) for r in rows]
        closed = self._build_closed(executions)
        names = sorted(set(signal_counts) | set(execution_counts) | {t.strategy_name for t in closed})
        performances = tuple(self._aggregate(name, int(signal_counts.get(name,0)), int(execution_counts.get(name,0)), tuple(t for t in closed if t.strategy_name==name)) for name in names)
        now = self.now_provider()
        if now.tzinfo is None:
            raise ValueError("現在日時にはタイムゾーンが必要です。")
        return StrategyAnalyticsReport(now.astimezone(timezone.utc), str(self.database_path.resolve()), performances, tuple(closed))

    @staticmethod
    def _build_closed(executions):
        entries = defaultdict(deque)
        closed = []
        for e in executions:
            key = (e['strategy_name'], e['code'])
            if e['action']=='buy' or e['side']=='buy':
                item = dict(e); item['remaining']=e['quantity']; entries[key].append(item); continue
            if e['action'] not in {'sell','exit'} and e['side']!='sell':
                continue
            remaining = e['quantity']
            while remaining>0 and entries[key]:
                entry = entries[key][0]
                qty = min(entry['remaining'], remaining)
                ec = (entry['commission']+entry['slippage']) * qty / entry['quantity']
                xc = (e['commission']+e['slippage']) * qty / e['quantity']
                pnl = (e['execution_price']-entry['execution_price'])*qty-ec-xc
                closed.append(StrategyClosedTrade(e['strategy_name'],e['code'],entry['execution_id'],e['execution_id'],entry['executed_at'],e['executed_at'],qty,entry['execution_price'],e['execution_price'],ec,xc,pnl))
                entry['remaining'] -= qty; remaining -= qty
                if entry['remaining']==0: entries[key].popleft()
        return closed

    @staticmethod
    def _aggregate(name, signal_count, execution_count, trades):
        profits=[t.realized_profit_loss for t in trades if t.realized_profit_loss>0]
        losses=[t.realized_profit_loss for t in trades if t.realized_profit_loss<0]
        be=sum(t.realized_profit_loss==0 for t in trades)
        gp=sum(profits); gl=sum(losses); net=sum(t.realized_profit_loss for t in trades)
        equity=peak=dd=0.0
        for t in sorted(trades,key=lambda x:(x.exit_at,x.code)):
            equity += t.realized_profit_loss; peak=max(peak,equity); dd=max(dd,peak-equity)
        n=len(trades)
        return StrategyPerformance(name,signal_count,execution_count,n,len(profits),len(losses),be,gp,gl,net,gp/len(profits) if profits else None,gl/len(losses) if losses else None,len(profits)/n if n else None,gp/abs(gl) if gl<0 else (float('inf') if gp>0 else None),sum(t.holding_minutes for t in trades)/n if n else None,dd)

    @staticmethod
    def _dt(value: str) -> datetime:
        dt=datetime.fromisoformat(value)
        if dt.tzinfo is None: dt=dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
