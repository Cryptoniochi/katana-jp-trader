"""戦略別Analyticsレポートを生成するCLI。"""
import argparse
from pathlib import Path
from app.runtime.strategy_analytics_service import StrategyAnalyticsService
from app.runtime.strategy_analytics_reporter import StrategyAnalyticsReporter

def build_argument_parser():
    p=argparse.ArgumentParser()
    p.add_argument('--database-path',type=Path,default=Path('data/katana.db'))
    p.add_argument('--output-directory',type=Path,default=Path('reports/strategy'))
    return p

def run(arguments=None):
    a=build_argument_parser().parse_args(arguments)
    report=StrategyAnalyticsService(a.database_path).analyze()
    paths=StrategyAnalyticsReporter(a.output_directory).write(report)
    print(f'Strategies: {len(report.performances)}')
    print(f'Closed trades: {len(report.closed_trades)}')
    for p in paths: print(p)
    return 0

if __name__=='__main__': raise SystemExit(run())
