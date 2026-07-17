from datetime import time
from app.backtest.optimization_models import OrbOptimizationParameters
from app.backtest.optimization_result_models import OptimizationRunStatus,OrbOptimizationRunResult,OrbOptimizationResult
from app.backtest.optimization_ranking import OptimizationRankingService,RankingMetric
from app.backtest.performance_metrics_models import BacktestPerformanceMetrics

def m(n):
    return BacktestPerformanceMetrics(1,int(n>0),int(n<0),int(n==0),max(n,0),max(-n,0),n,1.0 if n>0 else 0.0,2.0 if n>0 else 0.0,None,None,n,1 if n>0 else 0,1 if n<0 else 0,0,0)
def r(i,n):
    return OrbOptimizationRunResult(parameter=OrbOptimizationParameters(0.02,0.04,time(9,10+i)),status=OptimizationRunStatus.COMPLETED,metrics=m(n),equity_curve_report=None)
def test_rank():
    res=OrbOptimizationResult(runs=(r(1,100),r(2,300),r(3,200)))
    ranked=OptimizationRankingService().rank(res,metric=RankingMetric.NET_PROFIT)
    assert ranked[0].run.net_profit_loss==300
