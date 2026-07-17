from dataclasses import dataclass
from enum import StrEnum
from app.backtest.optimization_result_models import OrbOptimizationResult, OrbOptimizationRunResult

class RankingMetric(StrEnum):
    NET_PROFIT='net_profit'
    PROFIT_FACTOR='profit_factor'
    WIN_RATE='win_rate'
    MAX_DRAWDOWN='max_drawdown'

@dataclass(frozen=True, slots=True)
class RankedOptimizationResult:
    rank:int
    run:OrbOptimizationRunResult

class OptimizationRankingService:
    def rank(self,result:OrbOptimizationResult,*,metric:RankingMetric,top_n:int|None=None):
        runs=list(result.completed_runs)
        if metric is RankingMetric.NET_PROFIT:
            runs.sort(key=lambda r:(r.net_profit_loss or float('-inf'),r.parameter_id),reverse=True)
        elif metric is RankingMetric.PROFIT_FACTOR:
            runs.sort(key=lambda r:(r.profit_factor or float('-inf'),r.parameter_id),reverse=True)
        elif metric is RankingMetric.WIN_RATE:
            runs.sort(key=lambda r:(r.win_rate or float('-inf'),r.parameter_id),reverse=True)
        else:
            runs.sort(key=lambda r:(r.maximum_drawdown if r.maximum_drawdown is not None else float('inf'),r.parameter_id))
        if top_n is not None:
            runs=runs[:top_n]
        return tuple(RankedOptimizationResult(i+1,r) for i,r in enumerate(runs))
