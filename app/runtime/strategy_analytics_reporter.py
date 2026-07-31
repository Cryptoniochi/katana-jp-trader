"""戦略別AnalyticsをJSON・CSV・HTMLへ出力する。"""
from __future__ import annotations
import csv, json, math
from dataclasses import asdict
from html import escape
from pathlib import Path

class StrategyAnalyticsReporter:
    def __init__(self, output_directory: Path) -> None:
        self.output_directory = Path(output_directory)

    def write(self, report):
        self.output_directory.mkdir(parents=True, exist_ok=True)
        jp=self.output_directory/'strategy_performance.json'; cp=self.output_directory/'strategy_performance.csv'; hp=self.output_directory/'strategy_performance.html'
        payload={'generated_at':report.generated_at.isoformat(),'database_path':report.database_path,'performances':[self._safe(asdict(x)) for x in report.performances],'closed_trades':[self._safe({**asdict(x),'entry_at':x.entry_at.isoformat(),'exit_at':x.exit_at.isoformat()}) for x in report.closed_trades]}
        jp.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
        fields=['strategy_name','signal_count','execution_count','completed_trade_count','win_count','loss_count','break_even_count','win_rate','gross_profit','gross_loss','net_profit_loss','profit_factor','average_profit','average_loss','average_holding_minutes','maximum_drawdown']
        with cp.open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=fields); w.writeheader()
            for x in report.performances:
                row=asdict(x); w.writerow({k:self._safe(row[k]) for k in fields})
        rows=[]
        for x in report.performances:
            wr='N/A' if x.win_rate is None else f'{x.win_rate:.2%}'
            pf='N/A' if x.profit_factor is None else ('∞' if math.isinf(x.profit_factor) else f'{x.profit_factor:.2f}')
            rows.append(f'<tr><td>{escape(x.strategy_name)}</td><td>{x.signal_count}</td><td>{x.execution_count}</td><td>{x.completed_trade_count}</td><td>{wr}</td><td>{pf}</td><td>{x.net_profit_loss:,.2f}</td><td>{x.maximum_drawdown:,.2f}</td></tr>')
        hp.write_text('<!doctype html><html lang="ja"><meta charset="utf-8"><title>KATANA Strategy Analytics</title><style>body{font-family:system-ui;margin:32px}table{border-collapse:collapse;width:100%}th,td{border:1px solid #ccc;padding:9px;text-align:right}th:first-child,td:first-child{text-align:left}th{background:#eee}</style><h1>Project KATANA Strategy Analytics</h1><p>生成日時: '+escape(report.generated_at.isoformat())+'<br>DB: '+escape(report.database_path)+'</p><table><tr><th>Strategy</th><th>Signals</th><th>Executions</th><th>Trades</th><th>Win Rate</th><th>PF</th><th>Net P/L</th><th>Max DD</th></tr>'+''.join(rows)+'</table></html>',encoding='utf-8')
        return jp,cp,hp

    @staticmethod
    def _safe(value):
        if isinstance(value,float) and math.isinf(value): return 'Infinity'
        if isinstance(value,dict): return {k:StrategyAnalyticsReporter._safe(v) for k,v in value.items()}
        if isinstance(value,list): return [StrategyAnalyticsReporter._safe(v) for v in value]
        return value
